# 테스트 및 검증 계획 

> **최종 수정일:** 2026-10-26

---

## 1. 테스트 원칙

| 원칙 | 내용 |
| --- | --- |
| TDD 우선 | 라우팅 판정·비용 계산·창 집계·누락률 등 지표 계산 로직은 **단위 테스트 선작성**이 필수다(SDD.md 비기능 요구사항) |
| 설명 가능성 | AI가 생성한 코드도 테스트가 통과해야 한다. PR마다 테스트 커버리지를 포함한다 |
| 격리 | 외부 API(LLM·Slack) 호출은 `RecordedLLMClient`, `NullNotifier` 등 더미 구현체로 격리한다(interfaces.md 9.1 더미 구현체) |
| 재현성 | 확률적 동작이 있는 테스트는 시드를 고정하거나 결정적 경로만 검증한다 |
| 실패 기록 | 실패한 테스트도 PR에서 `skip` 처리하지 않고 해결한 뒤 병합한다 |

---

## 2. 단위 테스트 (8.1-x, TDD 필수 대상)

> 인터페이스 계약 테스트(interfaces.md 9.2)와 겹치지 않도록 비즈니스 로직에 집중한다.
> 

### 8.1-1: `Router.route` — 경계값 및 분포 수렴

| 항목 | 내용 |
| --- | --- |
| **목적** | τ·r 경계값과 라우팅 사유 분류의 정확성 검증 |
| **관련** | interfaces.md `Router`, policies.md 3.2 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| τ=0.0, r=0.0 | score=0.5 | `to_stage2=True, reason="threshold"` |
| τ=1.0, r=0.0 | score=0.9 | `to_stage2=False, reason="none"` |
| τ=0.5, r=0.0 | score=0.5 | `to_stage2=True, reason="threshold"` (경계 포함) |
| τ=0.5, r=0.0 | score=0.4 | `to_stage2=False, reason="none"` |
| τ=0.5, r=1.0 | score=0.4 | `to_stage2=True, reason="sample"` |
| 임계값 우선 | score ≥ τ이면서 sample 추첨 당첨 | `reason="threshold"` (threshold 우선, interfaces.md 7.4 불변식) |
| 표본 수렴 | r=0.1, 시드 고정, n=10,000 | `sample` 비율 ≈ 0.1 ± 0.01 |

**불변식 검증** (interfaces.md 7.4에서 발췌)

```python
# 모든 결과에 대해:
assert (result.to_stage2 == True) == (result.reason in ("threshold", "sample"))
assert (result.to_stage2 == False) == (result.reason == "none")
# threshold가 sample보다 먼저 선택됨:
assert all(r.reason == "threshold"
           for r in results if r.score >= threshold)
```

### 8.1-2: `CostCalculator.calculate` — 비용 계산 정확도

| 항목 | 내용 |
| --- | --- |
| **목적** | 단가표 기반 계산과 할인 적용 정확성 |
| **관련** | interfaces.md `CostCalculator`, ADR-025 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 기본 계산 | 입력 1000토큰, 출력 200토큰 | 단가표 × 토큰 수 ≈ 소수점 6자리 |
| Batch API 할인 | `batch_api=True` | 기본 × 0.5 |
| 캐시 적중 | `cached_input_tokens=500` | 캐시 토큰은 할인 단가 적용 |
| 모델 없음 | 단가표에 없는 모델 | `PricingNotFoundError` 발생, 0 반환 금지 |
| 반올림 정밀도 | 임의 토큰 수 | 결과가 `NUMERIC(12,6)` 범위 내 |

```python
# 실제 청구액과 1회 이상 대조(ADR-025)
# 오차 허용 범위는 SP2 측정 후 확정
```

### 8.1-3: 창 집계 — `traces.started_at` 기준 배분

| 항목 | 내용 |
| --- | --- |
| **목적** | erd.md 1장 "창 집계 기준 = `traces.started_at`" 원칙 준수 검증 |
| **관련** | erd.md 1장·7장 정합성 규칙 6번, policies.md 3.4 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 비동기 처리 지연 | `started_at`=09:04, `evaluations.created_at`=09:06 | 09:00~09:05 창에 포함 |
| 경계 시각 | `started_at` = 창 시작 시각 정확히 | 해당 창에 포함 (창 시작 포함) |
| 창 경계 | `started_at` = 창 종료 시각 정확히 | 다음 창에 포함 (창 종료 미포함) |

### 8.1-4: 누락률 계산

| 항목 | 내용 |
| --- | --- |
| **목적** | `routed_reason='sample'` 표본 기반 누락률 추정 정확성 |
| **관련** | policies.md 3.2, SDD.md B-2 지표 |

**검증 케이스**: 전수 채점 기준 환각 100건 중 1단계가 놓친 10건 → 누락률 = 0.1. 무작위 표본 r=0.1에서 추정한 누락률이 실제 누락률의 95% 신뢰구간 내에 수렴하는지 확인(n=10,000 시뮬레이션).

### 8.1-5: 인터페이스 계약 테스트 — 배치 순서·점수 범위

| 항목 | 내용 |
| --- | --- |
| **목적** | interfaces.md 7.4 불변식 전체를 더미 구현체로 검증 |
| **관련** | interfaces.md 9.2, `StubDetector`, `StubJudge` |

**필수 검증 불변식** (interfaces.md 7.4에서 발췌)

```python
# 배치 순서 보장
assert [r.trace_id for r in results] == [i.trace_id for i in inputs]
# 점수 범위
assert all(0.0 <= r.score <= 1.0 for r in results)
# stage 1: 높을수록 의심 (방향 확인은 시나리오 테스트에서)
# stage 2: 높을수록 품질 좋음 (방향은 교차 검증으로 확인)
# HallucinationSpan 오프셋
assert all(span.text == answer[span.start:span.end]
           for span in result.spans)
# DriftVerdict 불변식
if verdict.deferred:
    assert verdict.is_drift == False
    assert verdict.drift_score is None
```

---

## 3. 통합 테스트 (8.2-x)

> DB와 워커를 포함한 동작을 검증한다. Docker Compose 환경에서 실행한다.
> 

### 8.2-1: `traces`·`eval_jobs` 동일 트랜잭션 보장

| 항목 | 내용 |
| --- | --- |
| **목적** | "저장은 됐는데 검사는 안 된" 유실 상태가 발생하지 않음을 확인 |
| **관련** | ADR-004, erd.md eval_jobs 비고, policies.md 3.1 |

**시나리오**

1. Ingest API로 트레이스 1건을 정상 저장 → `traces`와 `eval_jobs` 모두 존재
2. `traces` INSERT 직후 DB 연결을 강제 끊기(세션 종료) → 두 테이블 모두 존재하지 않음 (롤백)
3. `eval_jobs` INSERT 실패 시뮬레이션 → `traces`도 존재하지 않음

**합격 조건**: 어떤 경우에도 `traces`가 있고 `eval_jobs`가 없는 상태는 발생하지 않는다.

### 8.2-2: 수집 경로 장애 시 RAG 서비스 정상 동작

| 항목 | 내용 |
| --- | --- |
| **목적** | 감시가 감시 대상을 멈추지 않는다 |
| **관련** | ADR-001, policies.md 비기능 요구사항 "수집 장애 격리", policies.md 6.2 Fallback |

**시나리오**

1. OTel Collector 컨테이너를 강제 종료
2. RAG 서비스로 요청 100건 전송
3. 응답 성공률 측정

**합격 조건**: 응답 성공률 **100%**. `BatchSpanProcessor`가 전송 실패를 삼기고 서비스를 차단하지 않는다.

### 8.2-3: 워커 비정상 종료 시 `eval_jobs` 재시도

| 항목 | 내용 |
| --- | --- |
| **목적** | stale lock 회수 후 검사가 정상 완료됨을 확인 |
| **관련** | ADR-004, erd.md eval_jobs 비고, policies.md 2.1 (stale lock 5분) |

**시나리오**

1. 워커가 배치를 점유(`RUNNING` 상태)한 뒤 프로세스를 강제 종료
2. 5분 경과
3. 스케줄러가 stale lock을 회수하고 `PENDING`으로 복귀 + `attempts` 증가 확인
4. 새 워커가 작업을 재점유해 `DONE`으로 완료

**합격 조건**: `eval_jobs.attempts`가 2이고 최종 상태가 `DONE`.

### 8.2-4: 동일 `trace_id` 중복 수집 멱등 처리

| 항목 | 내용 |
| --- | --- |
| **목적** | SDK 재전송이 중복 검사를 만들지 않음 |
| **관련** | erd.md uq_traces_trace_id, policies.md 3.1 |

**시나리오**: 같은 `trace_id`로 Ingest API에 2회 요청 전송

**합격 조건**: 두 번째 요청은 `DUPLICATE_TRACE` 409 반환(또는 `duplicated` 카운트). `eval_jobs`는 1건만 존재한다.

### 8.2-5: 2단계 채점 `stage=2` 행 선행 조건 검증

| 항목 | 내용 |
| --- | --- |
| **목적** | 같은 트레이스의 1단계 결과 없이 2단계 행이 삽입되지 않음 |
| **관련** | erd.md 7장 정합성 규칙 3번, policies.md 3.2 |

**합격 조건**: `stage=1` 없이 `stage=2`만 삽입 시도 → 애플리케이션 계층에서 거부.

### 8.2-6: 라우팅 정책 변경 시 `version_changes` 기록

| 항목 | 내용 |
| --- | --- |
| **목적** | `PUT /routing-policy` 호출이 변경 이력을 생성하는지 확인 |
| **관련** | ADR-005, policies.md 3.3, api.md 6.3 |

**시나리오**: τ=0.5, r=0.05로 정책을 변경

**합격 조건**: `version_changes`에 `kind='routing', source='console'`인 행이 1건 생성된다. 같은 값으로 재적용 시 이력이 생성되지 않는다(동일 내용 재배포는 변경이 아님).

### 8.2-7: 인시던트 알림 중복 발송 방지 (두 겹 방어)

| 항목 | 내용 |
| --- | --- |
| **목적** | 같은 인시던트로 같은 채널에 알림이 두 번 발송되지 않음 |
| **관련** | erd.md uq_notifications_incident_channel, policies.md 3.6 |

**시나리오**: 같은 `incident_id`·`channel`로 알림 발송 2회 시도

**합격 조건**: 두 번째 시도는 `uq_notifications_incident_channel` 제약에 의해 거부된다. Slack Webhook에는 1회만 발송.

### 8.2-8: 드리프트 판정기 3종 동일 창 독립 기록

| 항목 | 내용 |
| --- | --- |
| **목적** | 같은 창에 대해 3종 판정기가 각각 독립적으로 `quality_windows` 행을 만드는지 확인 |
| **관련** | erd.md uq_quality_windows, policies.md 3.4 |

**합격 조건**: `metric='quality_score', window_start='2026-11-18T09:00:00Z', window_size_sec=300`에 대해 `fixed_threshold`, `ks_test`, `embedding_distance` 각각 1행씩 총 3행 존재.

### 8.2-9: 주입 실험 중복 실행 방지

| 항목 | 내용 |
| --- | --- |
| **목적** | `RUNNING` 상태 회차가 있을 때 새 실행이 거부됨 |
| **관련** | erd.md injection_runs, policies.md 3.7, api.md 9.2 |

**합격 조건**: `INJECTION_ALREADY_RUNNING` 409 반환. `injection_runs`의 `RUNNING` 행은 1건.

### 8.2-10: 에이전트 DB 계정 쓰기 거부

| 항목 | 내용 |
| --- | --- |
| **목적** | 에이전트용 read-only DB 계정이 실제로 쓰기를 거부하는지 확인 |
| **관련** | ADR-007, policies.md 1.3 `AGENT` 권한, erd.md 1장 에이전트 권한 |

**시나리오**: 에이전트 DB 계정으로 `incidents` 테이블에 UPDATE 시도

**합격 조건**: PostgreSQL이 `permission denied for table incidents` 오류로 거부한다. 애플리케이션 코드가 아니라 **DB 계정 권한**이 막는다.

### 8.2-11: `ABORTED` 회차 데이터 지표 집계 제외

| 항목 | 내용 |
| --- | --- |
| **목적** | 부분 주입 데이터가 지표를 오염시키지 않음 |
| **관련** | policies.md 3.7·9.2, injection-scenarios.md 9.2 |

**합격 조건**: `mode='experiment', status='ABORTED'`인 회차의 트레이스는 탐지율·정확도 집계 쿼리 결과에 포함되지 않는다.

### 8.2-12: 세션 만료·폐기 즉시 로그아웃

| 항목 | 내용 |
| --- | --- |
| **목적** | 만료·폐기된 세션으로 API 접근이 차단됨 |
| **관련** | ADR-017, policies.md 1.2·3.9 |

**시나리오 A** (만료): 세션 TTL을 1초로 설정 후 2초 뒤 API 호출 → `SESSION_EXPIRED` 401

**시나리오 B** (즉시 폐기): 계정 비활성화(`disabled_at` 기록) 후 기존 세션으로 API 호출 → `SESSION_REVOKED` 401. 세션 폐기는 계정 비활성화와 **동일 트랜잭션**에서 일어난다.

---

## 4. 성능 테스트 (8.3-x)

### 8.3-1: Console API 응답 시간 (p95 ≤ 1초)

| 항목 | 내용 |
| --- | --- |
| **목적** | 대시보드 조회 API가 응답 시간 SLA를 만족하는지 확인 |
| **관련** | SDD.md 비기능 요구사항, policies.md 5 |

**측정 대상**: `GET /api/v1/metrics/summary`, `GET /api/v1/metrics/timeseries`, `GET /api/v1/traces`, `GET /api/v1/incidents`

**측정 조건**: 트레이스 10만 건 이상 적재 상태, 동시 사용자 1명(단일 운영자 전제), Vultr vhp-4c-8gb

**합격 조건**:

| API | 평균 | p95 |
| --- | --- | --- |
| `/metrics/summary` | ≤ 100ms | ≤ 300ms |
| `/metrics/timeseries` | ≤ 200ms | ≤ 1,000ms |
| `/traces` 목록 | ≤ 150ms | ≤ 500ms |
| `/incidents` 목록 | ≤ 100ms | ≤ 300ms |

### 8.3-2: 계측 오버헤드 (p95 지연 차이 최소화)

| 항목 | 내용 |
| --- | --- |
| **목적** | 계측 SDK가 RAG 서비스 응답을 의미 있는 수준으로 지연시키지 않음 |
| **관련** | ADR-001, telemetry.md 8장, SDD.md 비기능 요구사항 |

**측정 절차**: telemetry.md 8장 비교군 ① ② ③. 예열 후 각 500회, 시드 고정.

**합격 조건**: 목표치는 SP2 1차 측정 후 확정. 최소한 "계측 켬"과 "계측 끔"의 p95 차이를 수치로 보고할 수 있어야 한다.

### 8.3-3: 검사 큐 처리량 (생성 속도 이상)

| 항목 | 내용 |
| --- | --- |
| **목적** | 검사 워커가 0.5 rps 수집 속도를 따라가는지 확인 |
| **관련** | ADR-006, policies.md 5 |

**합격 조건**: 0.5 rps 트래픽 30분 재생 후 `app.eval.queue.depth`가 단조 증가하지 않는다.

---

## 5. 보안 테스트 (8.4-x)

### 8.4-1: 비인증 접근 차단

**시나리오**: 세션 쿠키 없이 모든 Console API 엔드포인트 호출

**합격 조건**: 전부 `UNAUTHORIZED` 401 반환. `/health`와 `POST /auth/login`만 예외.

### 8.4-2: Ingest API 외부 접근 차단

**시나리오**: 서버 외부 IP에서 `/internal/v1/traces`로 요청

**합격 조건**: 연결 거부(네트워크 레벨 차단). `FORBIDDEN` 403이 아니라 TCP 연결 자체가 안 된다.

### 8.4-3: 에러 응답에 내부 정보 미포함

**시나리오**: 존재하지 않는 엔드포인트·잘못된 파라미터로 여러 500/400 에러 유도

**합격 조건**: 응답 바디에 스택 트레이스, SQL, 서버 내부 경로, `traces.question`·`answer` 내용이 포함되지 않는다(policies.md 6.3).

### 8.4-4: 비밀번호 해시 검증

**시나리오**: DB에서 `users.password_hash` 값 직접 확인

**합격 조건**: argon2id 형식(`$argon2id$...`)이다. bcrypt 형식이나 평문이 아니다(policies.md 1.4).

---

## 6. 인수 기준 체크리스트 (8.5-x)

SDD.md 각 기능의 인수 기준을 SP2·SP3 발표 전 점검하는 목록이다.

### SP2 데모 인수 기준 (필수)

| ID | 항목 | 확인 방법 | 상태 |
| --- | --- | --- | --- |
| 8.5-01 | 계측 SDK 적용 후 트레이스에 버전 3종 모두 연결 | 콘솔 트레이스 상세 화면에서 `versions.prompt/model/retrieval` 3종 표시 | ⬜ |
| 8.5-02 | 1단계 검사 전수 완료 — 미검사 트레이스 0건 | `SELECT COUNT(*) FROM traces t LEFT JOIN eval_jobs j ON j.trace_pk=t.id WHERE j.status!='DONE' AND t.status='OK'` = 0 | ⬜ |
| 8.5-03 | 2단계 `routed_reason` 분포 확인 | 콘솔 대시보드의 라우팅 분포 패널 표시 | ⬜ |
| 8.5-04 | 로그인·대시보드·트레이스 화면 SP2 통합 | 로컬 Docker Compose에서 접근 가능 (서버 배포는 8.5-07, SP3) | ⬜ |
| 8.5-05 | SCN-001 수동 주입으로 품질 그래프 하락 시연 | 시연 중 `quality_score` 시계열이 30분 이후 하락 확인 | ⬜ |
| 8.5-06 | 채점자 신뢰도 화면 1차 결과 표시 | MT-Bench 일치율·kappa·혼동 행렬 표시 | ⬜ |
| 8.5-07 | Vultr 배포 후 데모 리허설 1회 무중단 완주 (SP3) | 90분 시나리오 완주 + 알림 수신 | ⬜ |

### SP3 완성 인수 기준

| ID | 항목 | 확인 방법 | 상태 |
| --- | --- | --- | --- |
| 8.5-10 | 드리프트 감지 시 Slack 알림 자동 발송 | SCN-001~005 각 1회 실행, `notifications.status='SENT'` 확인 | ⬜ |
| 8.5-11 | 에이전트가 원인 후보를 구조화 JSON으로 반환 | `incidents.agent_result` 필드에 `rank/changeId/confidence/evidence` 포함 | ⬜ |
| 8.5-12 | Top-1 정확도 > 규칙 기반 기준선 | protocol.md 과제 D 지표, `agent_fallback=false` 인시던트 대상 | ⬜ |
| 8.5-13 | 탐지율·탐지 지연·오탐 횟수를 방식별로 비교한 표 제출 | protocol.md 과제 C, 시나리오 5종×10회 | ⬜ |
| 8.5-14 | 비용 절감률 수치와 계측값–실제 청구액 오차 보고 | ADR-025, protocol.md 과제 B-2 | ⬜ |
| 8.5-15 | 동일 시드로 재실행 시 동일 결과 재현 | SCN-001을 시드 42로 2회 실행해 `traces` 순서 동일 확인 | ⬜ |
| 8.5-16 | 정확도–효율 곡선 (1단계 탐지 모델) | protocol.md 과제 A 산출물 | ⬜ |

---

## 7. CI/CD 검증 (8.6-x)

| ID | 항목 | 트리거 | 합격 조건 |
| --- | --- | --- | --- |
| 8.6-01 | 단위 테스트 전체 통과 | PR → main | 8.1-x 전체 pass |
| 8.6-02 | 통합 테스트 통과 | PR → main | 8.2-x 전체 pass |
| 8.6-03 | Docker 빌드 성공 | PR → main | 빌드 오류 없음 |
| 8.6-04 | Alembic 마이그레이션 무결성 | `migrations/` 변경 시 | `alembic upgrade head` 오류 없음 |
| 8.6-05 | 비밀값 커밋 방지 | PR → main | `.env`·API 키 패턴 감지 시 차단 |
| 8.6-06 | Vultr 자동 배포 | main 병합 | 배포 후 `/health` 응답 `status: "UP"` |

---

## 8. 테스트 환경

| 환경 | 용도 | 구성 |
| --- | --- | --- |
| 로컬 Docker Compose | 단위·통합 테스트 | `docker-compose.test.yml`. 외부 API는 더미 구현체 |
| Vultr vhp-4c-8gb | 성능·인수 테스트 | 실제 LLM 호출 포함. 실험 시간 외 서버 destroy (`runbook.md`) |
| CI (GitHub Actions) | 자동화 | 로컬 Docker Compose 환경과 동일 |

---

## 미결정 사항

| # | 항목 | 담당 | 기한 |
| --- | --- | --- | --- |
| TP-1 | 8.3-2 계측 오버헤드 목표치 — SP2 1차 측정 후 확정 | `BOTH` | SP2 |
| TP-2 | 8.5-12 Top-1 정확도 목표 수치 — SP2 1차 실험 후 확정(기획서 미결정 A-3) | `BOTH` | SP2 |
| TP-3 | 8.5-14 비용 절감률 목표 수치 — 동일 | `BOTH` | SP2 |
| TP-4 | 다중 비교 보정(Holm 등) 적용 여부 — 버전별 A/B 비교 화면에서 여러 지표를 동시 검정할 때(protocol.md 참고절) | `AI-MDL` | SP3 |

---

end.