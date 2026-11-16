# 텔레메트리

> **최종 수정**: 2026-10-26

---

## 1. 개요

| 항목 | 값 |
| --- | --- |
| 계측 프레임워크 | OpenTelemetry (OTel) — Python SDK |
| 시맨틱 컨벤션 버전 | **리비전 고정.** `gen_ai.*` 속성이 Development 단계이므로 적용 리비전을 `configs/otel/semconv.lock`에 기록하고 매핑 계층을 둔다 (ADR-002). 구체 리비전은 SP2 9주차 확정(미결정) |
| 백엔드 | **계층 A**: OTel Collector → Ingest API → PostgreSQL / **계층 B**: OTel Collector → Prometheus → Grafana |
| 수집 대상 | **계층 A**: Traces (Metrics·Logs 미수집) / **계층 B**: Metrics + Logs |
| 샘플링 전략 | **100% (샘플링하지 않는다)** — 아래 참조 |
| 전송 방식 | OTLP/HTTP, 비동기 배치(BatchSpanProcessor) |
| 보존 | 계층 A는 논문 투고까지(policies.md 7장), 계층 B 메트릭 15일·로그 14일 |

**샘플링을 하지 않는 이유**

이 플랫폼의 핵심 주장은 "표본 검사가 아닌 **전수 감시**"다. 수집 단계에서 샘플링하면 1단계 전수 검사의 모집단이 이미 표본이 되어 주장 자체가 무너진다. 2단계 LLM 채점에서의 `sample_rate`는 **수집 샘플링이 아니라 비용 라우팅**이며 누락률 측정 장치다. 둘을 혼동하지 않는다(policies.md 3.2).

### 1.1 두 계층의 데이터 경로

| 구분 | 계층 A (감시 대상) | 계층 B (플랫폼 자체) |
| --- | --- | --- |
| 생성 주체 | RAG 서비스 + 계측 SDK | Ingest·Worker·Drift·Agent·Console API |
| 신호 종류 | Traces | Metrics, Logs |
| 경로 | SDK → Collector → Ingest API → DB | 각 프로세스 → Collector → Prometheus → Grafana |
| 소비자 | 품질 검사 워커, 콘솔, 에이전트 | 팀(운영 점검), Grafana 임베드 패널 |
| 장애 시 | **드롭**. 서비스 응답을 막지 않는다 | 드롭. 운영 가시성만 저하 |
| 문서 위치 | 2~4장 | 5~7장 |

---

## 2. 수집 설정

### 2.1 계측 포인트

| 계측 대상 | 계층 | 방식 | 비고 |
| --- | --- | --- | --- |
| HTTP 요청 (인바운드) | A·B | Auto | `opentelemetry-instrumentation-fastapi` |
| LLM 호출 | A | **Manual** | `@trace_llm` 데코레이터. `gen_ai.*` 직접 기록 |
| 벡터 검색 (pgvector) | A | **Manual** | 검색 문맥·top-k를 스팬 속성으로 남겨야 하므로 자동 계측으로 부족 |
| 프롬프트 조립 | A | **Manual** | 어떤 버전으로 조립했는지 기록 |
| DB 쿼리 | B | Auto | `opentelemetry-instrumentation-psycopg` — 계층 B만 활성화 |
| 검사 워커 | B | Manual | 배치 크기·단계별 지연 메트릭 |
| Drift Monitor | B | Manual | 창 집계 소요·판정 결과 카운터 |
| 에이전트 루프 | B | Manual | 도구 호출 수·토큰. 조사 과정 자체는 DB(`agent_steps`)가 원본 |
| 외부 API 호출 (Slack) | B | Manual | 발송 성공·실패 카운터 |

계층 A에서는 DB 자동 계측을 끈다. 켜 두면 pgvector 쿼리가 수백 개 스팬으로 쏟아져 `spans` 테이블이 불필요하게 커진다.

### 2.2 컨텍스트 전파

- **전파 형식**: W3C TraceContext (`traceparent`, `tracestate`)
- **비동기 경계에서 트레이스를 잇지 않는다.** 검사 워커의 작업은 원래 요청과 수 초~수 분 떨어져 실행된다. 같은 트레이스로 이으면 스팬 하나의 지속 시간이 비정상적으로 길어져 지연 통계가 오염된다. 대신 `eval_jobs.trace_pk`와 `evaluations.trace_pk`가 DB 수준에서 연결을 보장한다(ADR-004).
- 워커 스팬에는 `app.trace_ref`로 원본 trace id를 **속성으로만** 남겨 조사 시 연결할 수 있게 한다.

### 2.3 전송·버퍼 설정

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 프로세서 | `BatchSpanProcessor` | 동기 전송은 사용자 응답을 막는다(ADR-001) |
| 배치 전송 주기 | 5초 | policies.md 2.1 |
| 배치 큐 상한 | 512 스팬 | 초과분은 드롭 |
| 전송 실패 처리 | 재시도 2회(1s → 3s) 후 **드롭** | 수집이 서비스를 막지 않는 것이 우선(policies.md 6.1) |
| Collector 메모리 한도 | 256MB | ADR-013 |
| OTLP 엔드포인트 | 내부 네트워크 전용 | policies.md 1.5 |

---

## 3. 스팬 명세

스팬 이름에 가변 값(trace id, 질문 내용, 사용자명)을 넣지 않는다. 가변 값은 속성으로 기록한다.

### 3.1 스팬 목록

**계층 A — 감시 대상 RAG 서비스** (DB `spans` 테이블에 저장)

| 스팬 이름 | Kind | `spans.kind` | 설명 |
| --- | --- | --- | --- |
| `rag.request` | SERVER | `OTHER` | RAG 요청 전체. 루트 스팬 |
| `rag.retrieve` | INTERNAL | `RETRIEVAL` | pgvector 검색 |
| `rag.build_prompt` | INTERNAL | `PROMPT` | 프롬프트 조립 |
| `gen_ai.chat` | CLIENT | `LLM` | LLM 생성 호출 |

**계층 B — 플랫폼 자체** (Prometheus 메트릭으로 집계, DB 저장 안 함)

| 스팬 이름 | Kind | 설명 |
| --- | --- | --- |
| `ingest.receive` | SERVER | 트레이스 배치 수신·저장 |
| `eval.stage1` | INTERNAL | 1단계 배치 추론 |
| `eval.stage2` | CLIENT | 2단계 LLM 채점 |
| `drift.evaluate` | INTERNAL | 시간 창 집계·판정 |
| `agent.investigate` | INTERNAL | 에이전트 조사 1건 |
| `console.api` | SERVER | Console API 요청 |

### 3.2 스팬 상세 — `rag.request`

| 항목 | 값 |
| --- | --- |
| **계층** | A |
| **Kind** | SERVER |
| **설명** | RAG 요청 전체. 이 스팬의 trace id가 `traces.trace_id`가 되고, 모든 검사·채점이 여기에 연결된다 |

**속성**

| 속성 키 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `http.request.method` | string | Y | `POST` |
| `http.route` | string | Y | `/chat` |
| `http.response.status_code` | int | Y | 200 / 5xx |
| `service.name` | string | Y | 감시 대상 서비스 식별자 |
| `app.version.prompt` | string | Y | 프롬프트 버전명 |
| `app.version.model` | string | Y | 모델 설정 버전명 |
| `app.version.retrieval` | string | Y | 검색 설정 버전명 |
| `app.version.prompt_id` | int | Y | `versions.id` — Ingest가 FK 연결 |
| `app.version.model_id` | int | Y | 동일 |
| `app.version.retrieval_id` | int | Y | 동일 |
| `app.injection.run_id` | string | N | 주입 실험 회차 UUID. 평상시 미기록 |
| `app.content.question` | string | Y | 질문 전문. 크기 상한 4.3 참조 |
| `app.content.answer` | string | N | 응답 전문. 생성 실패 시 미기록 |
| `app.cost.usd` | double | Y | 요청 단위 비용(`CostCalculator`) |
| `app.cost.pricing_version` | string | Y | 적용 단가표 버전 |

**비고**: 버전 ID와 버전명을 둘 다 기록한다. ID는 Ingest가 FK를 거는 데 쓰고, 이름은 사람이 읽는 화면과 에이전트 설명에 쓴다. 버전 3종이 모두 없으면 그 트레이스는 원인 분석·A/B 비교 모집단에서 빠진다(policies.md 3.1).

### 3.3 스팬 상세 — `rag.retrieve`

**속성**

| 속성 키 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `app.retrieval.top_k` | int | Y | 요청한 문서 수 |
| `app.retrieval.chunk_size` | int | Y | 청크 크기 |
| `app.retrieval.doc_count` | int | Y | **실제로** 반환된 문서 수 |
| `app.retrieval.doc_ids` | string[] | Y | 문서 식별자 목록 |
| `app.retrieval.top_score` | double | N | 최고 유사도 |
| `app.content.contexts` | string | Y | 검색 문맥 전문(JSON). 크기 상한 4.3 참조 |

**비고**: `top_k`와 `doc_count`를 따로 기록한다. 둘이 다르면 검색 인덱스 손상(SCN-005 주입 시나리오)이 일어난 것이다. 이 차이가 탐지 신호가 된다.

### 3.4 스팬 상세 — `rag.build_prompt`

**속성**: `app.version.prompt`, `app.prompt.template_hash`(템플릿 해시, `versions.content_hash`와 일치해야 함), `app.prompt.char_count`

**비고**: `template_hash`가 `versions.content_hash`와 다르면 배포 중 설정이 꼬인 것이므로 경보 대상이다.

### 3.5 스팬 상세 — `gen_ai.chat`

**속성**

| 속성 키 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `gen_ai.provider.name` | string | Y | `anthropic`. 표준 속성은 `gen_ai.provider.name` (ADR-002 리비전 고정 확인 후 적용) |
| `gen_ai.operation.name` | string | Y | `chat` |
| `gen_ai.request.model` | string | Y | 요청 모델 식별자 |
| `gen_ai.request.max_tokens` | int | N | — |
| `gen_ai.request.temperature` | double | N | — |
| `gen_ai.response.model` | string | N | **실제로 응답한** 모델. 요청과 다를 수 있다 |
| `gen_ai.response.finish_reasons` | string[] | N | 길이 초과로 잘렸는지 판단 |
| `gen_ai.usage.input_tokens` | int | Y | — |
| `gen_ai.usage.output_tokens` | int | Y | — |
| `app.cost.usd` | double | Y | 이 호출의 비용 |
| `app.llm.retry_count` | int | N | 재시도 횟수. 지연 해석에 필요 |

**비고**

- 토큰 수는 응답 수신 후에만 기록할 수 있다. 스팬 종료 직전에 속성을 추가한다.
- `gen_ai.response.model`을 따로 남기는 이유는 제공자가 요청 모델을 내부적으로 교체할 수 있기 때문이다(SCN-002 시나리오와 연결된 탐지 포인트).
- 표준 속성(`gen_ai.*`)과 자체 속성(`app.*`)을 분리한다. 표준이 바뀌어도 자체 속성은 영향을 받지 않는다(ADR-002).

---

## 4. 속성 표

| 속성 키 | 타입 | 설명 |
| --- | --- | --- |
| `gen_ai.provider.name` | string | LLM 공급자 |
| `gen_ai.operation.name` | string | 작업 종류(`chat`) |
| `gen_ai.request.model` | string | 요청 모델명 |
| `gen_ai.request.max_tokens` | int | 최대 출력 토큰 |
| `gen_ai.request.temperature` | double | 샘플링 온도 |
| `gen_ai.response.model` | string | 실제 응답 모델명 |
| `gen_ai.response.finish_reasons` | string[] | 종료 사유 |
| `gen_ai.usage.input_tokens` | int | 입력 토큰 수 |
| `gen_ai.usage.output_tokens` | int | 출력 토큰 수 |
| `http.request.method` | string | HTTP 메서드 |
| `http.route` | string | 라우트 패턴(가변 값 금지) |
| `http.response.status_code` | int | 응답 상태 코드 |
| `db.system.name` | string | DB 종류 (계층 B만) |
| `service.name` | string | 서비스 식별자 |
| `exception.type` | string | 예외 분류 |

적용 리비전은 `configs/otel/semconv.lock`에 고정한다. 리비전을 올릴 때 이 표를 함께 점검한다.

### 4.2 커스텀 속성 (`app.*`)

| 속성 키 | 타입 | 스팬 | 설명 |
| --- | --- | --- | --- |
| `app.version.prompt` | string | `rag.request`, `rag.build_prompt` | 프롬프트 버전명 |
| `app.version.model` | string | `rag.request` | 모델 설정 버전명 |
| `app.version.retrieval` | string | `rag.request` | 검색 설정 버전명 |
| `app.version.prompt_id` | int | `rag.request` | `versions.id` |
| `app.version.model_id` | int | `rag.request` | 동일 |
| `app.version.retrieval_id` | int | `rag.request` | 동일 |
| `app.prompt.template_hash` | string | `rag.build_prompt` | 템플릿 내용 해시 |
| `app.prompt.char_count` | int | `rag.build_prompt` | 조립 길이 |
| `app.retrieval.top_k` | int | `rag.retrieve` | 요청 문서 수 |
| `app.retrieval.chunk_size` | int | `rag.retrieve` | 청크 크기 |
| `app.retrieval.doc_count` | int | `rag.retrieve` | 실제 반환 문서 수 |
| `app.retrieval.doc_ids` | string[] | `rag.retrieve` | 문서 식별자 목록 |
| `app.retrieval.top_score` | double | `rag.retrieve` | 최고 유사도 |
| `app.content.question` | string | `rag.request` | 질문 전문 |
| `app.content.answer` | string | `rag.request` | 응답 전문 |
| `app.content.contexts` | string | `rag.retrieve` | 검색 문맥 JSON |
| `app.cost.usd` | double | `rag.request`, `gen_ai.chat` | 비용 |
| `app.cost.pricing_version` | string | `rag.request` | 단가표 버전 |
| `app.llm.retry_count` | int | `gen_ai.chat` | 재시도 횟수 |
| `app.injection.run_id` | string | `rag.request` | 주입 실험 회차 |
| `app.trace_ref` | string | 계층 B 스팬 | 원본 trace id (비동기 경계 연결용) |
| `app.ingest.batch_size` | int | `ingest.receive` | 수신 배치 크기 |
| `app.ingest.accepted` | int | `ingest.receive` | 저장 성공 건수 |
| `app.eval.batch_size` | int | `eval.stage1` | 추론 배치 크기 |
| `app.eval.detector` | string | `eval.stage1` | 1단계 탐지 평가자 식별자. 형식: `{모델명}-{서빙형식}`. interfaces.md `Detector.name` 참조 (예: `lettucedetect-modernbert-base-onnx-int8`) |
| `app.eval.judge` | string | `eval.stage2` | 2단계 채점자 식별자. interfaces.md `Judge.name` 참조 |
| `app.eval.routed_reason` | string | `eval.stage2` | 라우팅 사유 (`threshold`/`sample`) |
| `app.drift.detector` | string | `drift.evaluate` | 드리프트 판정기 식별자. erd.md `DriftDetectorName` Enum 값 (`fixed_threshold`/`ks_test`/`embedding_distance`) |
| `app.drift.window_sec` | int | `drift.evaluate` | 창 길이(초) |
| `app.drift.deferred` | boolean | `drift.evaluate` | 표본 부족 판정 보류 여부 |
| `app.agent.steps` | int | `agent.investigate` | 도구 호출 수 |
| `app.agent.fallback` | boolean | `agent.investigate` | 규칙 기반 대체 여부 |

Ingest API가 DB 컬럼으로 정규화하는 속성: `app.version.*`, `app.cost.*`, `app.retrieval.*`. 나머지는 `spans.attributes` JSONB에 원본 그대로 남는다(erd.md 5장).

### 4.3 본문 속성의 크기 제한

| 속성 | 상한 | 초과 시 |
| --- | --- | --- |
| `app.content.question` | 8KB | 뒤를 자르고 `app.content.question_truncated=true` |
| `app.content.answer` | 32KB | 동일 |
| `app.content.contexts` | 128KB | 문서 단위로 뒤에서부터 제외하고 `app.content.contexts_truncated=true` |
| 스팬 1개 총합 | 192KB | 초과 스팬 드롭 + 계층 B 카운터 증가 |

잘린 본문은 1단계 탐지의 입력도 잘린다. api.md 3.3의 `truncated` 처리와 기준을 맞춰야 한다(미결정).

### 4.4 금지 속성

| 금지 항목 | 이유 |
| --- | --- |
| trace id·span id를 **메트릭 레이블**로 쓰기 | 카디널리티 폭발 |
| 질문·응답 본문을 **메트릭 레이블**로 쓰기 | 동일 |
| 속성 키에 가변 값 넣기 | 동일 |
| API 키·세션 토큰·Webhook URL | 비밀값 유출(policies.md 1.4) |
| 사용자 IP·식별자 | 수집하지 않는 정보 |
| 예외 메시지 원문 | 본문이 섞여 들어올 수 있다. `exception.type`과 분류 코드만 남긴다 |

---

## 5. 메트릭 명세

모두 **계층 B**다.

| 메트릭명 | 유형 | 단위 | 설명 | 레이블 |
| --- | --- | --- | --- | --- |
| `gen_ai.client.operation.duration` | Histogram | ms | LLM 호출 지연 | `provider`, `model`, `operation` |
| `gen_ai.client.token.usage` | Counter | tokens | 누적 토큰 | `model`, `type`(input/output) |
| `app.llm.cost.usd` | Counter | USD | 누적 LLM 비용 | `model`, `purpose`(generation/judge/agent) |
| `app.ingest.traces.count` | Counter | — | 수집 트레이스 수 | `result`(accepted/duplicated/rejected) |
| `app.eval.queue.depth` | Gauge | — | 검사 대기 작업 수 | — |
| `app.eval.job.duration` | Histogram | ms | 작업 1건 처리 시간 | `stage`(1/2) |
| `app.eval.stage1.batch_size` | Histogram | — | 1단계 배치 크기 | `detector` |
| `app.eval.routed.count` | Counter | — | 라우팅 판정 수 | `reason`(threshold/sample/none) |
| `app.eval.job.failed` | Counter | — | 검사 실패 | `reason`(inference/llm/parse) |
| `app.drift.window.evaluated` | Counter | — | 평가한 시간 창 수 | `detector`, `metric`, `deferred` |
| `app.drift.detected.count` | Counter | — | 저하 판정 수 | `detector`, `metric` |
| `app.incident.created.count` | Counter | — | 생성된 인시던트 수 | `metric` |
| `app.agent.investigation.duration` | Histogram | ms | 조사 1건 소요 | `fallback` |
| `app.agent.tool.calls` | Counter | — | 도구 호출 수 | `tool_name` |
| `app.notification.sent.count` | Counter | — | 알림 발송 | `channel`, `status` |
| `http.server.request.duration` | Histogram | ms | API 응답 시간 | `route`, `status_code` |
| `http.server.request.count` | Counter | — | 수신 요청 수 | `route`, `method`, `status_code` |
| `container_memory_usage_bytes` | Gauge | bytes | 컨테이너 메모리 | `container` |
| `pg_stat_database_*` | Gauge | — | DB 커넥션·트랜잭션 | `database` |

**레이블 설계 원칙**

- 레이블 값의 가짓수를 수십 개 이하로 유지한다.
- **버전명(`app.version.prompt`)은 레이블로 쓰지 않는다.** 실험 중 버전이 계속 늘어나 시계열이 무한히 분기한다. 버전별 집계는 Prometheus가 아니라 **DB 쿼리**로 한다(api.md 2.4).
- `app.eval.queue.depth`는 이 시스템의 **가장 중요한 운영 지표**다. 이 값이 단조 증가하면 검사가 생성 속도를 못 따라간다는 신호이며, 전수 검사 전제가 무너지고 있다는 뜻이다.

---

## 6. 로그 명세

### 6.1 로그 레벨 정책

| 레벨 | 사용 기준 |
| --- | --- |
| `ERROR` | 처리 불가 예외, 외부 API 최종 실패, 검사 작업 `FAILED`, 알림 발송 실패 |
| `WARN` | 재시도 발생, stale lock 회수, 표본 부족 판정 보류, 본문 잘림, 지출 한도 임박 |
| `INFO` | 요청 시작·완료, 버전 변경 감지, 인시던트 생성·종료, 주입 실행, 로그인·로그아웃 |
| `DEBUG` | 개발·디버깅용. 프로덕션 비활성화 |

**구조화 로그 필수 필드**: `timestamp`(ISO 8601 UTC), `level`, `logger`(모듈명), `message`, `trace_id`(해당 시), `request_id`(API 요청이면 `X-Request-Id`)

### 6.2 민감 정보 제외 규칙

로그에 절대 포함하지 않는 값: 비밀번호, API 키, 세션 토큰 원문, Slack Webhook URL, **사용자 질문·LLM 응답 본문**, 예외 메시지 원문, DB 연결 문자열·SQL 전문.

본문을 스팬에는 넣고 로그에는 넣지 않는 이유: 스팬의 본문은 제품의 기능(품질 검사·하이라이트에 필요, 로그인 뒤 콘솔에서만 조회)이고, 로그의 본문은 부수 효과(14일 보관·평문 파일·터미널 출력 경로로 통제가 약하다).

---

## 7. 대시보드·알림 임계값

### 7.1 핵심 대시보드 패널

**플랫폼 운영 대시보드 (Grafana, 계층 B)**

| 패널명 | 메트릭 | 비고 |
| --- | --- | --- |
| API 응답 시간 | `http.server.request.duration` p50/p95/p99 | Console API 기준 |
| 에러율 | `http.server.request.count` 5xx 비율 | — |
| **검사 큐 적체** | `app.eval.queue.depth` | **가장 먼저 보는 패널** |
| 검사 처리량 | `app.eval.job.duration` p95, 초당 처리 건수 | `stage`별 분리 |
| 1단계 추론 지연 | `app.eval.job.duration{stage="1"}` p95 | CPU 서빙 건전성 |
| LLM 호출 지연 | `gen_ai.client.operation.duration` p95 | `purpose`별 |
| 토큰·비용 누적 | `app.llm.cost.usd` 시간당 합계·누적 | 예산 추적 |
| 라우팅 분포 | `app.eval.routed.count` `reason`별 비율 | τ·r 적정성 점검 |
| 드리프트 판정 | `app.drift.detected.count` 판정기별 카운트 | 오탐 급증 감지 |
| 컨테이너 메모리 | `container_memory_usage_bytes` | 8GiB 한도 대비 |

### 7.2 알림 규칙

**알림 두 종류를 구분한다.**

| 구분 | 대상 | 판정 주체 | 경로 |
| --- | --- | --- | --- |
| **품질 알림** | 감시 대상 서비스의 품질 저하 | Drift Monitor (계층 A) | 인시던트 → `Notifier` → Slack `#quality` |
| **운영 알림** | 플랫폼 자체의 이상 | Grafana (계층 B) | Grafana → Slack `#ops` |

두 알림은 Slack 채널을 분리한다. 섞이면 시연 중 운영 경보가 품질 알림처럼 보인다.

**운영 알림 임계값** (Slack `#ops`)

| 알림명 | 조건 | 임계값 |
| --- | --- | --- |
| 검사 큐 적체 | `app.eval.queue.depth` | 500 초과 10분 지속 |
| 검사 실패 급증 | `app.eval.job.failed` 증가율 | 5분간 10건 초과 |
| API 에러율 급증 | 5xx 비율 | 1% 초과 5분 지속 |
| LLM 응답 지연 | `gen_ai.client.operation.duration` p95 | 30s 초과 5분 지속 |
| 예산 임박 | `app.llm.cost.usd` 누적 | 예산의 80% 도달 |
| 지출 한도 도달 | 2단계 채점 중단 상태 | 즉시 |
| 컨테이너 메모리 | `container_memory_usage_bytes` | 한도의 90% 초과 5분 |
| 수집 중단 | `app.ingest.traces.count` 증가 없음 | 10분간 0건(트래픽 있는 구간) |
| DB 커넥션 포화 | 활성 커넥션 | 상한의 90% |

---

## 8. 계측 오버헤드 측정

| 항목 | 내용 |
| --- | --- |
| 측정 지표 | 계측 적용/미적용 조건의 **p95 응답 지연 차이** |
| 측정 도구 | Locust 또는 k6 |
| 환경 | 배포 환경과 같은 Vultr vhp-4c-8gb. 다른 컨테이너 동시 가동 상태 포함 |
| 절차 | 예열 → 3회 반복 → 평균·편차 보고 |
| 비교군 | ① 계측 끔 ② 계측 켬(배치 전송) ③ 계측 켬 + Collector 중단(드롭 경로) |
| 보고 | 측정 조건(인스턴스·동시 실행·시드)을 수치와 함께 기록(policies.md 9.3) |

비교군 ③을 넣은 이유는 "수집 장애가 서비스에 영향을 주지 않는다"는 ADR-001의 주장을 같은 실험에서 함께 확인하기 위해서다. 목표치는 SP2 1차 측정 후 확정한다(미결정 A-3).

---

## 9. 표준 변경 대응

OTel GenAI 시맨틱 컨벤션은 Development 단계라 속성 이름이 바뀔 수 있다(ADR-002).

| 항목 | 규칙 |
| --- | --- |
| 리비전 고정 | `configs/otel/semconv.lock`에 기록. SDK가 기동 시 검증 |
| 매핑 계층 | 내부 도메인 이름 → 표준 속성 키 변환을 `src/sdk/semconv.py` 한 파일에 모음 |
| 자체 속성 분리 | `app.*`는 표준과 독립. 표준이 바뀌어도 영향 없음 |
| 변경 절차 | ① 새 리비전 확인 → ② 매핑 계층 수정 → ③ 4.1 표 갱신 → ④ ADR-002 갱신 → ⑤ 같은 PR |
| 금지 | **SP3 주입 실험 중 리비전 변경 금지.** 속성 이름이 바뀌면 구간 전후 데이터 비교가 깨진다(policies.md 9.2) |

---

## 미결정 사항

- [ ]  OTel GenAI 시맨틱 컨벤션 리비전 확정 (담당 `AI-SVC`, 기한 SP2 9주차)
- [ ]  본문 기록 방식 — `app.content.*` 속성 vs 규약 권장 이벤트·로그 방식 (담당 `AI-SVC`, 기한 SP3)
- [ ]  본문 잘림 기준과 하이라이트 오프셋 정합 — telemetry 4.3의 상한과 api.md 3.3의 `truncated` 처리 기준 일치 필요 (담당 `AI-SVC`, 기한 SP2)
- [ ]  `app.content.contexts` 저장 범위 — 문서 전문 vs ID+오프셋. erd.md 미결 D-2와 같은 사안 (담당 `AI-SVC`, 기한 SP2 9주차)
- [ ]  계층 B 트레이스 보존 여부 — 현재 메트릭만 남기고 스팬은 버린다. 워커 디버깅에 필요해지면 Tempo 도입 검토 (담당 `AI-SVC`, 기한 SP3)
- [ ]  운영 알림 Slack 채널 분리 구성 — 품질 알림과 다른 Webhook URL 필요 (담당 `AI-SVC`, 기한 SP3)
- [ ]  계측 오버헤드 목표치 — SP2 1차 측정 후 확정 (담당 `BOTH`, 기한 SP2)

---

end.