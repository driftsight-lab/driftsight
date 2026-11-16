# 다이어그램 v1.0

> 최종 수정일: 2026-10-31

---

## 0. 작성 규칙

### 작성 규칙

- 다이어그램은 Mermaid로 작성한다. 흐름은 `sequenceDiagram`, 상태는 `stateDiagram-v2`, 판정·분기는 `flowchart`를 쓴다.
- **정상 흐름만 그리지 않는다.** 필수 다이어그램에는 실패·중복·경합 경로를 `alt`/`opt`로 함께 넣는다.
- 각 절의 체크박스는 다이어그램이 실제 구현과 검증 완료되었을 때 체크한다.
- 모든 스팬 오프셋·점수 방향·Enum 값은 `인터페이스 계약`을 기준으로 맞춘다.

---

## 1. 전체 시스템 구성도

> 작성: BOTH
> 
- [x]  기획서 4.1 다이어그램과 동기화 완료 여부 확인

### 1.1 전체 아키텍처

```mermaid
flowchart TB
    User["사용자 / 트래픽 생성기"]
    Op["운영자 (로그인)"]
    LLM["Claude API\n생성(소형) · 채점·에이전트(중형)"]
    Slack["Slack\nIncoming Webhook"]

    subgraph Vultr["Vultr vhp-4c-8gb · Docker Compose"]
        direction TB
        CFG["configs/ 버전 파일\n프롬프트 · 모델 · 검색 설정\n(원본은 Git, DB는 해시 레지스트리)"]

        subgraph SVC_AREA["서비스 계층"]
            direction LR
            RAG["RAG 서비스\nFastAPI · 계측 SDK(OTel GenAI)"]
            ING["Ingest API\nFastAPI · 트레이스 저장 + 작업 등록"]
            CAPI["Console API\nFastAPI · 세션 인증(httpOnly 쿠키)"]
            CON["관제 콘솔\nNext.js · App Router · Recharts"]
        end

        subgraph WORKER_AREA["비동기 워커 계층 (요청 경로 분리)"]
            direction LR
            EW["Eval Worker\n1단계: ONNX INT8 전수 탐지\n2단계: LLM 선별 채점 + 임베딩"]
            DM["Drift Monitor\nAPScheduler · 5분 창 집계\nDriftDetector 3종 플러그인"]
            AG["원인 분석 에이전트\n직접 루프 구현 · MCP 조회 전용 도구\n최대 호출 횟수 · 토큰 한도 코드 통제"]
        end

        subgraph INFRA_AREA["인프라 계층"]
            direction LR
            COL["OTel Collector\notel-contrib · 256MB 한도\nOTLP 수신 → Ingest API / Prometheus"]
            DB[("PostgreSQL + pgvector\ntraces · versions · evaluations\nembeddings · incidents\nquality_windows · 작업 큐(SKIP LOCKED)")]
            PROM["Prometheus\n메트릭 수집"]
            GF["Grafana\n비용·지연 시계열 패널\n(콘솔 임베드 읽기 전용)"]
        end
    end

    User -->|"HTTP 요청"| RAG
    CFG -->|"버전 로드 (기동 시)"| RAG
    RAG -->|"생성 요청 (동기)"| LLM
    RAG -.->|"OTLP 배치 (비동기)"| COL
    COL -->|"트레이스 전달"| ING
    ING -->|"저장 + eval_job 등록 (단일 트랜잭션)"| DB
    DB -->|"SKIP LOCKED 선점"| EW
    EW -->|"채점 요청 (의심 + 표본)"| LLM
    EW -->|"1·2단계 결과 + 임베딩 저장"| DB
    DB -->|"창 집계 조회"| DM
    DM -->|"인시던트 생성"| DB
    DM -->|"분석 트리거"| AG
    AG -.->|"read-only MCP 조회"| DB
    AG -->|"agent_result 저장"| DB
    DM -->|"알림 발송"| Slack
    DB --> CAPI --> CON
    COL -->|"메트릭"| PROM --> GF
    Op -->|"HTTPS"| CON
```

> 실선: 동기 호출 / 점선: 비동기·조회 전용.
품질 검사·드리프트 감지·에이전트는 모두 사용자 응답 경로 밖에서 비동기로 동작한다.
> 

---

## 2. 텔레메트리 수집 흐름

> 작성: AI-SVC
> 
- [ ]  OTLP 배치 전송 실패 시 SDK 버퍼링·재시도 경로 구현 확인
- [ ]  버전 해시 중복 등록 방지 로직 확인 (versions 테이블 upsert)

### 2.1 RAG 요청 → 수집 파이프라인 (sequenceDiagram)

```mermaid
sequenceDiagram
    autonumber
    participant User as 사용자
    participant RAG as RAG 서비스<br/>(FastAPI + SDK)
    participant CFG as configs/ 버전 파일
    participant LLM as Claude API (소형)
    participant COL as OTel Collector
    participant ING as Ingest API
    participant DB as PostgreSQL

    Note over RAG,CFG: 기동 시 1회 — 버전 로드 및 DB 등록
    RAG->>CFG: 프롬프트·모델·검색 설정 로드
    RAG->>DB: versions 테이블에 content_hash로 upsert<br/>(동일 해시 → 기존 버전 재사용)

    Note over User,DB: 요청 흐름 (동기 응답 + 비동기 계측)
    User->>RAG: HTTP 요청 (질문)
    RAG->>RAG: SDK — OTel 스팬 시작,<br/>version_ids 부착
    RAG->>DB: pgvector 검색 (근거 문서 조회)
    DB-->>RAG: RetrievedDoc 목록

    RAG->>LLM: 생성 요청 (프롬프트 + 문맥)
    LLM-->>RAG: 생성 응답
    RAG-->>User: HTTP 응답 반환 ← 동기 경로 종료

    Note over RAG,COL: 비동기 계측 전송 (응답 후 배치)
    RAG-)COL: OTLP 배치 전송<br/>(스팬: 질문·응답·문맥·토큰·비용·지연·version_ids)

    alt OTLP 전송 실패 (네트워크·Collector 다운)
        RAG->>RAG: SDK 내부 버퍼에 보관, 백오프 재시도
        Note right of RAG: 버퍼 한도 초과 시 스팬 드롭<br/>(수집 실패가 서비스를 막지 않는다)
    end

    COL->>ING: 트레이스 전달 (OTLP HTTP)

    alt Ingest API 다운
        COL->>COL: Collector 자체 재시도 큐에 보관
    end

    ING->>DB: 단일 트랜잭션: traces 저장 + eval_jobs 등록
    Note right of DB: 트랜잭션 실패 시 롤백<br/>→ 해당 요청 기록 유실 (수용 가능)

    DB-->>ING: 커밋 완료
```

---

## 3. 2단 품질 검사 흐름

> 작성: BOTH
> 
- [ ]  BudgetExceededError 발생 시 1단계 유지·2단계 중단 처리 확인
- [ ]  SKIP LOCKED 선점 후 임대 시간 내 미완료 시 재선점 로직 확인 (policies.md)

### 3.1 Eval Worker — 검사 실행 흐름 (sequenceDiagram)

```mermaid
sequenceDiagram
    autonumber
    participant EW as Eval Worker
    participant DB as PostgreSQL<br/>(eval_jobs · traces · evaluations)
    participant DET as Detector<br/>(ONNX INT8, CPU)
    participant ROU as Router
    participant EMB as Embedder<br/>(all-MiniLM-L6-v2)
    participant JUD as Judge<br/>(Claude 중형)
    participant LLM as Claude API (중형)

    loop 폴링 루프
        EW->>DB: SELECT FOR UPDATE SKIP LOCKED<br/>(status=PENDING, locked_at 갱신)
        alt 처리 대기 작업 없음
            DB-->>EW: 빈 결과
            Note right of EW: 짧은 대기 후 재폴링
        end
    end

    EW->>DB: trace 데이터 조회 (question, answer, contexts)
    DB-->>EW: EvalInput 목록 (배치, 최대 16건)

    EW->>DET: detect_batch(inputs)
    Note right of DET: score 방향: 0.0(정상) → 1.0(환각 의심)

    alt DetectorInferenceError
        DET-->>EW: 예외 (retryable=True)
        EW->>EW: 백오프 재시도 (최대 3회)
        Note right of EW: 3회 초과 → job status=FAILED
    end

    DET-->>EW: list[DetectionResult] (score, spans, latency_ms)

    EW->>ROU: route(results, threshold=τ, sample_rate=r)
    Note right of ROU: threshold 판정 우선,<br/>이미 선택된 건은 표본 추첨 모집단에서 제외
    ROU-->>EW: list[RoutingDecision] (to_stage2, reason)

    EW->>DB: stage1 결과 저장 (evaluations, stage=1)

    opt to_stage2 == True (reason: "threshold" or "sample")
        par 병렬 실행
            EW->>EMB: embed_batch(answers)
            alt EmbeddingError
                EMB-->>EW: 예외
                Note right of EW: 임베딩 없이 진행 (품질 점수 검사는 유지)
            end
            EMB-->>EW: list[list[float]] (정규화, L2 norm=1)
        and
            EW->>JUD: judge_batch(inputs)
            JUD->>LLM: complete() × 배치 (채점 프롬프트)

            alt LLMRateLimitError (429)
                LLM-->>JUD: 429
                JUD-->>EW: LLMRateLimitError (retryable)
                EW->>EW: 백오프 재시도 (1s→4s→16s, 최대 3회)
            else LLMTransientError (5xx · 타임아웃)
                EW->>EW: 동일 재시도 정책
            else BudgetExceededError
                JUD-->>EW: BudgetExceededError (retryable=False)
                Note right of EW: 2단계 채점 전면 중단<br/>1단계 결과는 유지
            else LLMPermanentError (400/401/403)
                JUD-->>EW: LLMPermanentError (retryable=False)
                Note right of EW: 재시도 금지 → job FAILED + 경보
            end

            LLM-->>JUD: 채점 응답 (구조화)
            JUD->>JUD: 결과 파싱 (실패 시 1회 재시도 후 JudgeParseError)
            JUD-->>EW: list[JudgeResult] (score, label, reason, cost_usd)
            Note right of JUD: score 방향: 0.0(불량) → 1.0(양호)<br/>stage1 score와 방향이 반대
        end

        EW->>DB: stage2 결과 저장 (evaluations, stage=2)<br/>embeddings 저장 (pgvector)
    end

    EW->>DB: job status=DONE, attempts 갱신
```

### 3.2 라우팅 판정 로직 (flowchart)

```mermaid
flowchart TD
    IN["DetectionResult 목록 수신\n(score, trace_id)"]
    TH{"score ≥ τ ?"}
    S2_T["to_stage2=True\nreason='threshold'"]
    POOL["표본 추첨 모집단\n(임계값 미달 건만)"]
    SAMPLE{"무작위 추첨\n비율 r 적용"}
    S2_S["to_stage2=True\nreason='sample'"]
    SKIP["to_stage2=False\nreason='none'"]
    OUT["RoutingDecision 목록 반환\n(입력과 동일 길이·순서)"]

    IN --> TH
    TH -->|Yes| S2_T
    TH -->|No| POOL
    S2_T --> OUT
    POOL --> SAMPLE
    SAMPLE -->|추첨 당첨| S2_S
    SAMPLE -->|미당첨| SKIP
    S2_S --> OUT
    SKIP --> OUT

    style S2_T fill:#EBFBEE,stroke:#51CF66
    style S2_S fill:#E7F5FF,stroke:#339AF0
    style SKIP fill:#F1F3F5,stroke:#CED4DA
```

---

## 4. 드리프트 감지 및 알림 흐름

> 작성: BOTH
> 
- [ ]  쿨다운 중복 발송 억제 (dedup_key 기반) 구현 확인
- [ ]  표본 부족(sample_count < 30) 시 deferred 처리 확인
- [ ]  3종 판정기 중 일부 DriftInputError 발생 시 나머지 판정기 계속 실행 확인

### 4.1 Drift Monitor 주기 실행 (sequenceDiagram)

```mermaid
sequenceDiagram
    autonumber
    participant SCH as APScheduler<br/>(5분 주기)
    participant DM as Drift Monitor
    participant DB as PostgreSQL<br/>(traces · evaluations · quality_windows · incidents)
    participant DET1 as FixedThresholdDetector
    participant DET2 as KsTestDetector
    participant DET3 as EmbeddingDistanceDetector
    participant AG as 원인 분석 에이전트
    participant NTF as Notifier<br/>(SlackWebhookNotifier)
    participant Slack as Slack

    SCH->>DM: 5분 창 집계 트리거 (traces.started_at 기준)
    DM->>DB: 현재 창 WindowStats 조회<br/>(quality_score, hallucination_rate, embeddings)
    DB-->>DM: WindowStats (current)

    DM->>DB: 기준 구간 창 목록 조회 (baseline windows, N개)
    DB-->>DM: list[WindowStats] (baseline)

    Note over DM,DET3: 3종 판정기 각각 독립 호출 — 모두 결과를 기록한다

    par 고정 임계값 판정
        DM->>DET1: judge(current, baseline)
        alt DriftInputError (필요 필드 누락)
            DET1-->>DM: DriftInputError
            Note right of DM: 이 판정기만 건너뜀, 나머지 계속
        end
        DET1-->>DM: DriftVerdict (fixed_threshold)
    and KS 검정 판정
        DM->>DET2: judge(current, baseline)
        alt sample_count < 30
            DET2-->>DM: DriftVerdict(deferred=True, is_drift=False)
        end
        DET2-->>DM: DriftVerdict (ks_test)
    and 임베딩 거리 판정
        DM->>DET3: judge(current, baseline)
        alt embeddings 필드 없음
            DET3-->>DM: DriftInputError
        end
        DET3-->>DM: DriftVerdict (embedding_distance)
    end

    DM->>DB: quality_windows 저장 (3종 판정 결과 각각 1행)

    alt 하나 이상 is_drift == True
        DM->>DB: incidents 테이블에 인시던트 생성 (status=OPEN)
        DB-->>DM: incident_id

        DM->>AG: 원인 분석 트리거 (incident_id 전달)
        Note right of AG: 에이전트 루프 — 상세는 5절 참조
        AG-->>DM: agent_result (원인 후보 순위·근거)

        DM->>DB: incident.agent_result 갱신

        DM->>DB: dedup_key로 notifications 조회 (쿨다운 확인)
        alt 쿨다운 중 (동일 dedup_key 내 최근 알림 존재)
            Note right of DM: 중복 발송 억제 — 알림 생략
        else 쿨다운 해제
            DM->>NTF: send(NotificationPayload)
            NTF->>Slack: Webhook POST
            alt NotificationTransientError (429·5xx·타임아웃)
                Slack-->>NTF: 오류
                NTF->>NTF: 백오프 재시도 (1s→5s→25s, 최대 3회)
            else NotificationPermanentError (400·404)
                Note right of NTF: 재시도 금지, 인시던트 처리는 계속
            end
            NTF-->>DM: 발송 완료
            DM->>DB: notifications 기록 (payload 스냅샷, dedup_key 갱신)
        end
    end
```

---

## 5. 원인 분석 에이전트 흐름

> 작성: AI-SVC
> 
- [ ]  최대 호출 횟수·토큰 한도 코드 통제 구현 확인 (ADR-007)
- [ ]  MCP 도구 — DB read-only 계정으로만 접근하는지 확인
- [ ]  에이전트 결론 미달 시 규칙 기반 대체(직전 변경 지목) 동작 확인

### 5.1 에이전트 루프 상세 (sequenceDiagram)

```mermaid
sequenceDiagram
    autonumber
    participant DM as Drift Monitor
    participant AG as 에이전트 루프<br/>(직접 구현, 프레임워크 없음)
    participant LLM as Claude API (중형)
    participant MCP as MCP 서버<br/>(조회 전용 도구)
    participant DB as PostgreSQL<br/>(read-only 계정)

    DM->>AG: 분석 시작 (incident_id, 감지된 지표·시각)

    Note over AG: 초기 컨텍스트 구성<br/>인시던트 정보 + 감지 시각 기준 N분 범위

    loop 에이전트 루프 (최대 호출 횟수 M, 토큰 한도 T)
        AG->>LLM: complete_with_tools(messages, tools)<br/>(Claude 중형 모델)
        LLM-->>AG: 응답

        alt kind == "tool_use"
            AG->>MCP: 도구 호출 (tool_name, tool_args)
            Note over MCP,DB: 사용 가능 MCP 도구<br/>- query_version_changes(time_range)<br/>- query_traces(time_range, filters)<br/>- query_evaluations(trace_ids)<br/>- query_incidents(filters)
            MCP->>DB: SELECT (read-only 계정)
            DB-->>MCP: 조회 결과
            MCP-->>AG: 도구 결과 (JSON)
            AG->>AG: messages에 tool_result 추가
        else kind == "final"
            AG->>AG: 루프 종료, 최종 보고서 생성
        end

        alt 최대 호출 횟수 M 초과
            Note right of AG: 조기 종료<br/>지금까지의 근거로 부분 보고서 작성
        else 토큰 한도 T 초과
            Note right of AG: 동일 — 부분 보고서로 종료
        end
    end

    AG->>DB: incident.agent_result 갱신<br/>(원인 후보 순위, 근거 요약, 조사 과정)
    AG-->>DM: agent_result 반환

    opt 에이전트가 원인 후보를 지목하지 못한 경우
        Note right of DM: 규칙 기반 대체:<br/>감지 시각 직전 version_changes에서<br/>가장 최근 변경을 Top-1으로 지목
    end
```

---

## 6. 관제 콘솔 화면 흐름

> 작성: AI-SVC (운영 화면) / AI-MDL (실험 화면)
> 
- [ ]  세션 인증(httpOnly 쿠키) — 로그인 만료 시 리다이렉트 동작 확인 (ADR-017)
- [ ]  Grafana 패널 임베드 — 읽기 전용 + 콘솔 로그인 후에만 노출 확인
- [ ]  A/B 비교 화면: 표본 수·유의성 함께 표시 여부 확인

### 6.1 화면 전환 흐름 (flowchart)

```mermaid
flowchart LR
    LOGIN["로그인 화면\n(세션 쿠키 발급)\n[AI-SVC · SP2]"]

    subgraph OP_AREA["운영 화면 [AI-SVC]"]
        DASH["품질 관제 대시보드\n품질 점수·환각 비율·비용·지연 시계열\n버전 변경 시점 주석 오버레이\n[SP2 기본 → SP3 완성]"]
        TRACE["요청 트레이스 상세\n근거 없는 구간 하이라이트\n채점 이유·버전·비용\n[SP2]"]
        INC["인시던트 상세\n에이전트 조사 과정\n원인 후보 순위·근거\n[SP3]"]
        NOTIF["알림 설정\nSlack Webhook URL 관리\n쿨다운 정책 설정\n[SP3 권장]"]
    end

    subgraph EXP_AREA["실험 화면 [AI-MDL]"]
        TRUST["채점자 신뢰도\nMT-Bench 일치율·Cohen's kappa\n[SP2]"]
        AB["버전별 A/B 비교\n점수 분포·환각 비율·비용·지연\n표본 수·통계적 유의성\n[SP3]"]
        ROUTE["2단 검사 라우팅 정책\nτ·r 슬라이더\n정확도-비용 곡선·예상 절감액\n[SP3]"]
    end

    GRAFANA["Grafana 패널 임베드\n비용·지연 시계열만\n(읽기 전용)"]

    LOGIN --> DASH
    DASH --> TRACE
    DASH --> INC
    DASH --> TRUST
    DASH --> AB
    DASH --> NOTIF
    DASH -.-> GRAFANA
    INC --> TRACE
    INC --> AB
    AB --> ROUTE
```

---

## 7. 배포 및 인프라 구성도

> 작성: AI-SVC
> 
- [ ]  GitHub Actions SSH 배포 키 접속·`.env` SCP 주입 동작 확인 (ADR-020, ADR-021)
- [ ]  컨테이너별 mem_limit 설정 여부 확인 (ADR-014)
- [ ]  Secrets: 로컬 `.env` ↔ GitHub Secrets 2계층 분리 확인 (ADR-021)

### 7.1 CI/CD 파이프라인 (flowchart)

```mermaid
flowchart LR
    DEV["개발자\nmain 브랜치 push / PR 머지"]

    subgraph GH_ACTIONS["GitHub Actions"]
        direction TB
        CI["CI Job\n- uv 의존성 설치 (uv.lock)\n- pytest 단위·통합 테스트\n- 타입 검사 (mypy)"]
        BUILD["Build & Push Job\n- Docker 이미지 빌드\n- GHCR 푸시 (SHA 태그)\n(ADR-019)"]
        DEPLOY["Deploy Job\n- SSH Deploy Key로 Vultr 접속\n- docker compose pull (GHCR)\n- docker compose up -d\n(ADR-020)"]
    end

    GHCR["GHCR\n(GitHub Container Registry)\n이미지 저장소"]
    VULTR["Vultr vhp-4c-8gb\nDocker Compose 실행"]

    DEV -->|"git push"| CI
    CI -->|"테스트 통과"| BUILD
    BUILD -->|"이미지 push"| GHCR
    BUILD -->|"성공"| DEPLOY
    DEPLOY -->|"이미지 pull"| GHCR
    DEPLOY -->|"컨테이너 재기동"| VULTR

    CI -.->|"실패 시 배포 중단"| DEV
```

### 7.2 Docker Compose 컨테이너 구성 (flowchart)

```mermaid
flowchart TB
    subgraph VULTR["Vultr vhp-4c-8gb (4 vCPU · 8GB NVMe) · Docker Compose"]
        direction TB

        subgraph NET_IN["인터넷 노출 (포트 개방)"]
            RAG_C["rag-service\nFastAPI :8000"]
            CON_C["console-ui\nNext.js :3000"]
            COL_C["otel-collector\nOTLP HTTP :4318\nPrometheus :8889"]
            GF_C["grafana\n:3001 (읽기 전용 임베드)"]
        end

        subgraph NET_INT["내부 네트워크 전용"]
            ING_C["ingest-api\nFastAPI :8001"]
            CAPI_C["console-api\nFastAPI :8002"]
            EW_C["eval-worker\nPython 폴링 루프"]
            DM_C["drift-monitor\nAPScheduler"]
            AG_C["agent-runner\nMCP 서버 + 에이전트 루프"]
            DB_C[("postgresql\nPostgreSQL + pgvector\n:5432")]
            PROM_C["prometheus\n:9090"]
        end
    end

    RAG_C --> ING_C
    RAG_C --> COL_C
    COL_C --> ING_C
    COL_C --> PROM_C
    ING_C --> DB_C
    EW_C --> DB_C
    DM_C --> DB_C
    AG_C -.->|"read-only"| DB_C
    CAPI_C --> DB_C
    CON_C --> CAPI_C
    CON_C -.->|"패널 임베드"| GF_C
    PROM_C --> GF_C
```

---

## 8. 인터페이스 계층 구조

> 작성: BOTH
> 
- [ ]  인터페이스 계약 v1.1의 Protocol 정의와 동기화 확인

### 8.1 인터페이스 ↔ 구현체 관계 (flowchart)

```mermaid
flowchart LR
    subgraph CONSUMER["소비자 (Eval Worker · Drift Monitor · Agent)"]
        EWC["eval/worker.py"]
        DMC["drift/monitor.py"]
        AGC["agent/loop.py"]
    end

    subgraph IFACE["인터페이스 (src/interfaces/)"]
        direction TB
        DET_I["Detector\ndetect_batch()"]
        JUD_I["Judge\njudge_batch()"]
        ROU_I["Router\nroute()"]
        DRF_I["DriftDetector\njudge()"]
        EMB_I["Embedder\nembed_batch()"]
        LLM_I["LLMClient\ncomplete()\ncomplete_with_tools()"]
        COST_I["CostCalculator\ncalculate()"]
        NTF_I["Notifier\nsend()"]
    end

    subgraph IMPL["구현체 (configs/로 선택)"]
        direction TB
        DET_A["LettuceDetectDetector\n(기준선·임시)"]
        DET_B["OnnxTokenClassifierDetector\n(자체 학습 모델)"]
        JUD_A["ClaudeJudge"]
        JUD_B["CrossProviderJudge\n(교차 검증용)"]
        DRF_A["FixedThresholdDetector"]
        DRF_B["KsTestDetector"]
        DRF_C["EmbeddingDistanceDetector"]
        LLM_A["ClaudeClient"]
        NTF_A["SlackWebhookNotifier"]
        NTF_B["NullNotifier\n(테스트용)"]
    end

    EWC --> DET_I & JUD_I & ROU_I & EMB_I
    DMC --> DRF_I & NTF_I
    AGC --> LLM_I
    EWC & AGC --> LLM_I & COST_I

    DET_I -.-> DET_A & DET_B
    JUD_I -.-> JUD_A & JUD_B
    DRF_I -.-> DRF_A & DRF_B & DRF_C
    LLM_I -.-> LLM_A
    NTF_I -.-> NTF_A & NTF_B

    style IFACE fill:#E7F5FF,stroke:#339AF0
    style IMPL fill:#EBFBEE,stroke:#51CF66
```

---

## 9. eval_job 상태 전이

> 작성: AI-SVC
> 
- [ ]  FAILED 상태에서 수동 재처리 흐름 확인 (policies.md)
- [ ]  임대 시간 초과 시 PENDING 재전환 로직 확인 (SKIP LOCKED 임대 만료)

### 9.1 eval_jobs 상태 머신 (stateDiagram-v2)

```mermaid
stateDiagram-v2
    [*] --> PENDING : Ingest API가 트레이스 저장과\n동시에 등록 (단일 트랜잭션)

    PENDING --> IN_PROGRESS : Eval Worker가\nSKIP LOCKED 선점\n(locked_at 갱신)

    IN_PROGRESS --> PENDING : 임대 시간 초과\n(Worker 죽음 등)\n재선점 가능

    IN_PROGRESS --> DONE : 1단계 완료\n(2단계 미해당 포함)
    IN_PROGRESS --> DONE : 1단계 + 2단계 완료

    IN_PROGRESS --> FAILED : DetectorInferenceError\n3회 재시도 초과
    IN_PROGRESS --> FAILED : LLMPermanentError\n(재시도 금지)
    IN_PROGRESS --> FAILED : BudgetExceededError\n(1단계 결과는 유지)

    DONE --> [*]
    FAILED --> PENDING : 수동 재처리 요청\n(운영자 Console API 호출)
```

---

## 부록

### A. 서비스 간 종단 흐름

| 흐름 | 이어 붙일 절 | 상태 |
| --- | --- | --- |
| 요청 1건의 전체 생애: 진입 → 계측 → 수집 → 검사 → 결과 | 2.1 → 3.1 → 3.2 |  |
| 품질 저하 탐지 후 원인 지목 + 알림까지 | 4.1 → 5.1 |  |
| 운영자가 인시던트를 확인하고 트레이스까지 조회하는 흐름 | 4.1 → 6.1 |  |
| 버전 변경(configs/ 배포) 후 검사 결과가 갱신되는 흐름 | 7.1 → 2.1 → 3.1 |  |
| BudgetExceededError 발생 시 1단계 유지·전체 서비스 영향 흐름 | 3.1 (alt 분기) → 4.1 |  |
| 탐지 모델 교체 (LettuceDetect → 자체 ONNX 모델) | 8.1 → 3.1 |  |

---

end.