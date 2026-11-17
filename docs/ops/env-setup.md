# 환경 변수 설정 가이드

> **최종 수정일**: 2026-11-17
> 

---

## 사용법

```bash
cp .env.example .env
vim .env   # 아래 가이드를 보며 필수 값 입력
chmod 600 .env   # 소유자만 읽기·쓰기 (ADR-021)
```

---

## .env.example 파일

```bash
# ===================================================
# AISV Team17 — .env.example
# cp .env.example .env  →  vim .env 에서 값 채우기
# 절대 커밋 금지. 실제 비밀값은 GitHub Secrets에서 관리.
# ===================================================

# 🐳 Docker / Compose

COMPOSE_PROJECT_NAME=aisv
# COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml  # 로컬 override 시 주석 해제

# 🐘 PostgreSQL

POSTGRES_HOST_PORT=5433
POSTGRES_USER=aisv
POSTGRES_PASSWORD=                         # 필수 — openssl rand -hex 16
POSTGRES_DB=aisv
DATABASE_URL=postgresql+asyncpg://aisv:<PASSWORD>@postgres:5432/aisv

# 🔴 Redis

REDIS_HOST_PORT=6380                       # 충돌 시 6381 등으로 변경 (.env에서 조정)
REDIS_PASSWORD=                            # 필수
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# 🔭 OpenTelemetry Collector

OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318   # HTTP (gRPC 4317 미사용)
OTEL_SERVICE_NAME=rag-service              # 서비스별로 docker-compose.yml에서 오버라이드

# 🤖 LLM API — Anthropic Claude

ANTHROPIC_API_KEY=                         # 필수 — console.anthropic.com

# 생성(소형) / 채점·에이전트(중형) 등급 분리 (ADR-015)
LLM_GEN_MODEL=claude-haiku-4-5-20251001   # RAG 응답 생성용 (스냅샷 ID로 고정)
LLM_JUDGE_MODEL=claude-sonnet-4-5         # 2단계 채점 + 원인 분석 에이전트용

LLM_TIMEOUT_SECONDS=30                    # RAG 생성 타임아웃
LLM_JUDGE_TIMEOUT_SECONDS=60             # 채점·에이전트 타임아웃 (정책 상한 60s)
LLM_BUDGET_USD=200                        # 지출 한도 — 초과 시 2단계 채점 중단, 1단계 유지

# 🤗 HuggingFace Hub

HF_TOKEN=                         # private 레포 시 필수 — huggingface.co/settings/tokens
HF_HOME=/models/hf-cache          # 컨테이너 내부 캐시 경로 (볼륨 마운트와 일치 필수)

# 1단계 탐지 모델 — SP2에서는 기준선(LettuceDetect), 자체 모델 완성 후 교체 (ADR-027)
DETECTOR_REPO=KRLabsOrg/lettucedect-base-modernbert-en-v1
DETECTOR_REVISION=                         # 필수 — 태그 또는 커밋 해시, main 사용 금지
DETECTOR_FORMAT=onnx-int8                 # pytorch | onnx-fp32 | onnx-int8

# 임베딩 모델 (CPU 로컬 서빙 — Claude API 불필요)
EMBEDDING_REPO=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_REVISION=                        # 필수 — 커밋 해시 고정 (model-registry.md 5장 기입)

# 🔍 RAG 서비스 (backend/src/rag/)

RAG_PORT=8000
RAG_CORPUS_PATH=                           # 코퍼스 JSONL (model 파트 prepare_msmarco 출력 corpus.jsonl) — 적재 명령 입력
CONFIGS_DIR=configs                        # 버전 관리 설정 디렉토리 (컨테이너 /app/configs)

# 📥 Ingest API (backend/src/ingest/)

INGEST_PORT=8001
INGEST_BATCH_SIZE=100

# ⚙️ Worker (backend/src/worker/)

# 2단 라우팅 파라미터 (τ · r)
WORKER_ONNX_THRESHOLD=0.6                  # τ — 1단계 에스컬레이션 임계값. 낮출수록 LLM 비용↑
WORKER_SAMPLE_RATE=0.05                    # r — 2단계 무작위 표본 비율 (0으로 설정 시 누락률 측정 불가)

WORKER_LLM_STAGE_ENABLED=true             # false → 1단계(ONNX)만 실행, 초기 테스트·비용 절감용
WORKER_POLL_INTERVAL_SECONDS=2            # 폴링 간격(초) — 줄이면 지연↓ / DB 부하↑
WORKER_CONCURRENCY=4                       # 동시 워커 수 (서버 RAM 8GB 기준 4 권장)
WORKER_BATCH_WAIT_SECONDS=2               # 배치 대기 상한(초) — 먼저 도달한 조건(시간/건수) 실행
WORKER_BATCH_SIZE=16                       # 배치 최대 건수
WORKER_STALE_LOCK_SECONDS=300              # 검사 작업 점유 만료(초) — 초과 시 PENDING 복귀

# 📉 Drift Monitor (backend/src/drift/)

DRIFT_WINDOW_MINUTES=5                     # 판정 창 크기 (분)
DRIFT_THRESHOLD_RATIO=0.3                  # 창 내 이상 비율 임계값 (0.3 = 30% 초과 시 경보)
DRIFT_INCIDENT_COOLDOWN_MINUTES=15        # 동일 유형 인시던트 중복 방지 쿨다운
DRIFT_NOTIFY_COOLDOWN_MINUTES=30          # 동일 dedup_key 알림 재발송 억제 쿨다운

# 🕵️ Agent (backend/src/agent/)

AGENT_PORT=8004
AGENT_DB_DSN=postgresql+asyncpg://aisv_ro:<PASSWORD>@postgres:5432/aisv  # 읽기 전용 계정 필수
AGENT_MAX_CALLS=12                         # 도구 호출 상한 — 초과 시 규칙 기반 결과로 대체
AGENT_MAX_TOKENS=60000                     # 토큰 소비 상한

# 🖥️ Console (backend/src/console/)

CONSOLE_PORT=8002
CONSOLE_SECRET_KEY=                        # 필수 — openssl rand -hex 32 (32자 이상)
CONSOLE_ADMIN_EMAIL=admin@example.com
CONSOLE_ADMIN_PASSWORD=                    # 필수 — 12자 이상 권장

# 🌐 Frontend (Next.js)

FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=/api/v1               # NEXT_PUBLIC_ 접두사 → 브라우저 노출. 비밀값 입력 금지
                                           # 브라우저 → Next.js rewrite → console-api 프록시 경로

# 📊 Grafana

GRAFANA_PORT=3001
GF_SECURITY_ADMIN_PASSWORD=                # 필수

# 🔔 Slack 알림 (ADR-011)

# 두 채널을 분리한다. 섞이면 시연 중 운영 경보가 품질 알림처럼 보인다. (텔레메트리 문서 7.2)
SLACK_WEBHOOK_URL_QUALITY=                 # 필수 — 품질 드리프트 경보 (#quality)
SLACK_WEBHOOK_URL_OPS=                     # 권장 — 운영 이상 경보 (#ops). 없으면 QUALITY URL과 동일값 사용

# ☁️ 운영 서버 (Vultr) — 로컬 개발 시 불필요

VULTR_SERVER_IP=
IMAGE_TAG=latest                           # GHCR 이미지 태그 (운영에서는 sha-<커밋> 고정 권장)
```

---

## 섹션별 설명

### 🐳 Docker / Compose

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | `aisv` | 컨테이너·볼륨 이름에 붙는 prefix. 변경 불필요. |

```bash
# 로컬 개발 시 override 파일을 자동 로드하려면 주석 해제
# COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml
```

> 운영 서버에서는 위 줄을 주석 처리 상태로 유지한다.
> 

---

### 🐘 PostgreSQL

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `POSTGRES_HOST_PORT` | `5433` | — | 로컬 PC에서 접속할 포트 (컨테이너 내부는 5432 고정) |
| `POSTGRES_USER` | `aisv` | — | DB 사용자명. 변경 불필요. |
| `POSTGRES_PASSWORD` | *(비어 있음)* | **필수** | DB 비밀번호. 비워 두면 Compose 시작 거절. |
| `POSTGRES_DB` | `aisv` | — | DB 이름. 변경 불필요. |
| `DATABASE_URL` | `postgresql+asyncpg://aisv:<PASSWORD>@postgres:5432/aisv` | **필수** | `<PASSWORD>` 자리를 `POSTGRES_PASSWORD` 값으로 교체. |

**비밀번호 생성 예시:**

```bash
openssl rand -hex 16
# 예: a3f8c21d9b704e56...
```

---

### 🔴 Redis

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `REDIS_HOST_PORT` | `6380` | — | 로컬 PC 접속 포트 (컨테이너 내부는 6379 고정). 충돌 시 `6381` 등으로 변경. |
| `REDIS_PASSWORD` | *(비어 있음)* | **필수** | Redis 인증 비밀번호. 비워 두면 인증 없이 노출됨. |
| `REDIS_URL` | `redis://:${REDIS_PASSWORD}@redis:6379/0` | — | 서비스 내부 연결 URL. `REDIS_PASSWORD` 자동 치환. |

---

### 🔭 OpenTelemetry Collector

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | SDK가 스팬을 전송할 Collector **HTTP** 엔드포인트. gRPC(4317)는 미설정. |
| `OTEL_SERVICE_NAME` | `rag-service` | 스팬에 붙는 서비스 이름 태그. `docker-compose.yml`에서 서비스별로 오버라이드. |

> 이 값들은 `docker-compose.yml`에서 서비스별 `environment`로 오버라이드된다. `.env`에서 직접 변경해도 docker-compose가 최종 override 값을 사용한다.
> 

---

### 🤖 LLM API — Anthropic Claude

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | *(비어 있음)* | **필수** | RAG 응답 생성·2단계 채점·에이전트 전 기능에 사용. |
| `LLM_GEN_MODEL` | `claude-haiku-4-5-20251001` | — | RAG 응답 생성용 **소형** 모델 (ADR-015). 날짜 붙은 스냅샷 ID로 고정해 모델 변경을 버전 이력으로만 일으킨다 (ADR-005). |
| `LLM_JUDGE_MODEL` | `claude-sonnet-4-5` | — | 2단계 채점 + 원인 분석 에이전트용 **중형** 모델 (ADR-015). |
| `LLM_TIMEOUT_SECONDS` | `30` | — | RAG 생성 API 호출 타임아웃(초). |
| `LLM_JUDGE_TIMEOUT_SECONDS` | `60` | — | 채점·에이전트 API 호출 타임아웃(초). 정책 상한값. |
| `LLM_BUDGET_USD` | `200` | — | LLM 총 지출 한도(달러). 초과 시 2단계 채점 중단·1단계 유지 (정책 8장). |

**API 키 발급:**

1. console.anthropic.com 로그인
2. **API Keys → Create Key**
3. 생성된 키를 복사해 `.env`에 입력

> API 키는 생성 직후 한 번만 표시된다. 반드시 즉시 복사할 것.
> 

**모델 등급 분리 이유 (ADR-015):**

- 생성(소형)과 채점(중형)을 분리해 채점자 편향을 줄이고 비용을 최적화한다.
- 두 변수를 하나로 합치지 않는다.

---

### 🤗 HuggingFace Hub

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `HF_TOKEN` | *(비어 있음)* | 조건부 | private 레포는 필수. public 레포는 불필요. |
| `HF_HOME` | `/models/hf-cache` | — | 컨테이너 내부 모델 캐시 경로. 볼륨 마운트 경로와 일치해야 함. |
| `DETECTOR_REPO` | `KRLabsOrg/lettucedect-base-modernbert-en-v1` | — | 1단계 탐지 모델 HF 레포 ID. SP2는 LettuceDetect 기준선, 자체 모델 완성 후 교체 (ADR-027). |
| `DETECTOR_REVISION` | *(비어 있음)* | **필수** | 태그 또는 커밋 해시. **`main` 사용 금지** (model-registry.md 1장). |
| `DETECTOR_FORMAT` | `onnx-int8` | — | 서빙 형식. `pytorch` / `onnx-fp32` / `onnx-int8` 중 선택 (ADR-023). |
| `EMBEDDING_REPO` | `sentence-transformers/all-MiniLM-L6-v2` | — | 임베딩 모델 HF 레포 ID. CPU 서빙, 별도 API 비용 없음. |
| `EMBEDDING_REVISION` | *(비어 있음)* | **필수** | 임베딩 모델 고정 리비전. `model-registry.md` 5장 표에 기입. |

**리비전 고정 원칙 (model-registry.md 1장):**

- 외부 모델이 업데이트되면 1단계 점수 분포가 바뀐다.
- 이 시스템은 "변경으로 인한 품질 저하"를 탐지하는데, 스스로 리비전 미고정으로 변화를 일으키면 탐지 신뢰성이 무너진다.

**SP2 워커 구현 전 필수 작업:**

```bash
# 두 모델의 고정 리비전을 확인해 model-registry.md 5장 표와 .env에 모두 기입
pip install huggingface_hub
python -c "from huggingface_hub import model_info; print(model_info('KRLabsOrg/lettucedect-base-modernbert-en-v1').sha)"
python -c "from huggingface_hub import model_info; print(model_info('sentence-transformers/all-MiniLM-L6-v2').sha)"
```

**토큰 발급:**

1. huggingface.co/settings/tokens
2. **New token → Role: Read** 로 생성

---

### 🔍 RAG 서비스 (`backend/src/rag/`)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `RAG_PORT` | `8000` | RAG 서비스가 바인딩할 포트. 외부 공개. |
| `RAG_CORPUS_PATH` | *(비어 있음)* | 코퍼스 JSONL 경로. 코퍼스 적재 명령(`python -m src.rag.index_corpus`)이 읽어 `corpus_chunks`(pgvector)에 저장한다. 서비스 기동에는 필요 없다. |
| `CONFIGS_DIR` | `configs` | 버전 관리 설정(`configs/`) 경로. 기동 시 버전 등록과 프롬프트·모델·검색 설정 로드에 쓴다. |

---

### 📥 Ingest API (`backend/src/ingest/`)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `INGEST_PORT` | `8001` | OTel 스팬 수신 API 포트. **Docker 내부 네트워크 전용** — 외부 미노출. |
| `INGEST_BATCH_SIZE` | `100` | 한 번에 DB에 저장할 스팬 최대 개수. 너무 크면 메모리 압박. |

---

### ⚙️ Worker (`backend/src/worker/`)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `WORKER_ONNX_THRESHOLD` | `0.6` | **τ** — 1단계 ONNX 추론 에스컬레이션 임계값. 이 값 **이상**이면 2단계 LLM 검사로 넘어간다. 낮출수록 더 많이 LLM 검사 → 비용 증가. |
| `WORKER_SAMPLE_RATE` | `0.05` | **r** — 2단계 무작위 표본 비율. `0`으로 설정하면 누락률(miss rate) 측정 불가. |
| `WORKER_LLM_STAGE_ENABLED` | `true` | `false`로 설정하면 1단계 ONNX만 실행 (LLM 비용 없음). 초기 테스트 시 유용. |
| `WORKER_POLL_INTERVAL_SECONDS` | `2` | 작업 대기열 폴링 간격(초). 줄이면 레이턴시↓, DB 부하↑. |
| `WORKER_CONCURRENCY` | `4` | 동시 처리 워커 수. 서버 RAM **8GB** 기준 4 권장. mem_limit 1536m 고려. |
| `WORKER_BATCH_WAIT_SECONDS` | `2` | 배치 대기 상한(초). 2초 또는 BATCH_SIZE 건 중 먼저 도달한 조건에서 추론 실행 (정책 TTL 표). |
| `WORKER_BATCH_SIZE` | `16` | 한 번에 ONNX 추론할 최대 건수. |
| `WORKER_STALE_LOCK_SECONDS` | `300` | 검사 작업 점유 만료(초). `locked_at`이 이 시간을 넘긴 `RUNNING` 작업은 `PENDING`으로 되돌린다 (정책 TTL 표). |

> **불변식 (정책 2.2)**: `WORKER_BATCH_WAIT_SECONDS` < `DRIFT_WINDOW_MINUTES`(초 환산), `WORKER_STALE_LOCK_SECONDS` > `max(LLM_TIMEOUT_SECONDS, LLM_JUDGE_TIMEOUT_SECONDS)` 를 항상 만족해야 한다. 위반 시 기동이 중단된다.
> 

**임계값(τ) 조정 가이드:**

```
WORKER_ONNX_THRESHOLD 0.4 → 더 많이 잡힘, 비용↑, 오탐↑
WORKER_ONNX_THRESHOLD 0.6 → 기본값 (권장)
WORKER_ONNX_THRESHOLD 0.8 → 더 적게 잡힘, 비용↓, 미탐↑
```

평가셋 실험 결과(`docs/experiments/results/`)를 보고 최적값을 결정한다.

**표본 비율(r) 주의사항:**

- `WORKER_SAMPLE_RATE=0`으로 설정하면 2단계 무작위 표본이 없어 누락률(miss rate) 추정이 불가능하다.
- 콘솔 라우팅 정책 화면은 이 경우 경고를 표시하고 한 번 더 확인받는다 (API 명세서 6.3).

---

### 📉 Drift 판정 (`backend/src/drift/`)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `DRIFT_WINDOW_MINUTES` | `5` | 드리프트 판정 시간 창(분). 이 기간 내 데이터를 집계해 이상 비율 계산. |
| `DRIFT_THRESHOLD_RATIO` | `0.3` | 창 내 이상 비율이 이 값을 초과하면 드리프트로 판정. 0.3 = 30% 이상 시 경보. |
| `DRIFT_INCIDENT_COOLDOWN_MINUTES` | `15` | 동일 유형 인시던트 중복 생성 방지 쿨다운(분). |
| `DRIFT_NOTIFY_COOLDOWN_MINUTES` | `30` | 동일 `dedup_key` 알림 재발송 억제 쿨다운(분) (정책 TTL 표). |

**설정 판단 기준:**

| 상황 | 권장 조정 |
| --- | --- |
| 테스트 환경 (빠른 피드백) | `DRIFT_WINDOW_MINUTES=1`, `DRIFT_THRESHOLD_RATIO=0.1` |
| 운영 환경 (노이즈 줄이기) | `DRIFT_WINDOW_MINUTES=10`, `DRIFT_THRESHOLD_RATIO=0.4` |

> **불변식 (정책 2.2)**: `DRIFT_INCIDENT_COOLDOWN_MINUTES` ≥ `DRIFT_WINDOW_MINUTES`, `DRIFT_NOTIFY_COOLDOWN_MINUTES` ≥ `DRIFT_WINDOW_MINUTES` 를 항상 만족해야 한다. 위반 시 동일 인시던트·알림이 창마다 중복 생성될 수 있으며, 기동이 중단된다.
> 

---

### 🕵️ Agent (`backend/src/agent/`)

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `AGENT_PORT` | `8004` | — | 원인 분석 에이전트 API 포트. |
| `AGENT_DB_DSN` | `postgresql+asyncpg://aisv_ro:<PASSWORD>@postgres:5432/aisv` | **필수** | 에이전트 전용 **읽기 전용** DB 계정 DSN. `<PASSWORD>` 교체 필요. |
| `AGENT_MAX_CALLS` | `12` | — | 도구 호출 상한. 초과 시 규칙 기반 결과(`agent_fallback=true`)로 대체 (정책 3.5). |
| `AGENT_MAX_TOKENS` | `60000` | — | 토큰 소비 상한. 초과 시 동일하게 폴백. |

> Agent는 DB를 **조회 전용**으로만 접근해야 한다. 쓰기 권한이 있는 계정을 절대 사용하지 않는다 (ADR-007).
`aisv_ro` 계정은 Alembic 초기 마이그레이션에서 자동 생성된다.
> 

---

### 🖥️ Console (`backend/src/console/`)

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `CONSOLE_PORT` | `8002` | — | 관제 콘솔 백엔드 API 포트. frontend 프록시를 통해서만 접근. |
| `CONSOLE_SECRET_KEY` | *(비어 있음)* | **필수** | 세션 쿠키 서명 키. 최소 32자 이상 랜덤 문자열. |
| `CONSOLE_ADMIN_EMAIL` | `admin@example.com` | — | 초기 관리자 계정 이메일. |
| `CONSOLE_ADMIN_PASSWORD` | *(비어 있음)* | **필수** | 초기 관리자 비밀번호. 최소 12자 이상 권장. |

**Secret Key 생성:**

```bash
openssl rand -hex 32
# 예: 7f3a9b2c4d1e8f6a...
```

---

### 🌐 Frontend (Next.js)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `FRONTEND_PORT` | `3000` | Next.js 서버 포트. |
| `NEXT_PUBLIC_API_URL` | `/api/v1` | 프론트엔드 API 클라이언트 기본 URL. `next.config.ts`의 rewrite가 `/api/*`를 console-api로 프록시한다. |

> `NEXT_PUBLIC_` 접두사가 붙은 변수는 **브라우저에 노출**된다. 비밀값을 절대 넣지 않는다.
로컬·운영 모두 `/api/v1`(상대 경로)을 기본값으로 사용한다. Next.js rewrite가 내부적으로 console-api로 전달한다 (ADR-018).
> 

---

### 📊 Grafana

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `GRAFANA_PORT` | `3001` | — | Grafana 웹 UI 포트. |
| `GF_SECURITY_ADMIN_PASSWORD` | *(비어 있음)* | **필수** | Grafana 관리자(`admin`) 계정 비밀번호. |

접속: `http://localhost:3001` → ID: `admin` / PW: 설정한 비밀번호

---

### 🔔 Slack 알림 (`backend/src/drift/`, ADR-011)

| 변수 | 기본값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `SLACK_WEBHOOK_URL_QUALITY` | *(비어 있음)* | **필수** | 품질 드리프트 경보 채널 (`#quality`). |
| `SLACK_WEBHOOK_URL_OPS` | *(비어 있음)* | 권장 | 운영 이상 경보 채널 (`#ops`). 없으면 `QUALITY` URL 재사용. |

> **두 채널을 반드시 분리한다.** 섞이면 시연 중 운영 경보가 품질 알림처럼 보인다 (텔레메트리 문서 7.2).
Webhook URL은 유출 시 누구나 메시지를 발송할 수 있으므로 비밀값으로 취급한다 (ADR-021).
> 

---

### ☁️ 운영 서버 (Vultr) — 로컬 개발 시 불필요

| 변수 | 설명 |
| --- | --- |
| `VULTR_SERVER_IP` | Vultr 서버 퍼블릭 IP. CD 워크플로우 SSH 접속에 사용. |
| `IMAGE_TAG` | GHCR에서 Pull할 이미지 태그 (기본: `latest`). 운영에서는 `sha-<커밋>` 고정 권장. |

---

## 필수 값 체크리스트

`.env`를 채운 뒤 아래 항목이 모두 입력됐는지 확인한다.

```bash
# 빈 값이 있으면 출력됨
grep -E "^(POSTGRES_PASSWORD|REDIS_PASSWORD|ANTHROPIC_API_KEY|CONSOLE_SECRET_KEY|CONSOLE_ADMIN_PASSWORD|GF_SECURITY_ADMIN_PASSWORD|SLACK_WEBHOOK_URL_QUALITY|DETECTOR_REVISION|EMBEDDING_REVISION)=" .env | grep "=$"
```

출력이 없으면 모든 필수 값이 채워진 것이다.

| 변수 | 비워두면 발생하는 문제 |
| --- | --- |
| `POSTGRES_PASSWORD` | `docker compose up` 시작 거절 |
| `REDIS_PASSWORD` | Redis 인증 없이 노출 |
| `ANTHROPIC_API_KEY` | RAG 생성·2단계 LLM 검사·에이전트 기능 전면 불가 |
| `CONSOLE_SECRET_KEY` | 세션 쿠키 서명 불가 → 로그인 오류 |
| `CONSOLE_ADMIN_PASSWORD` | 관제 콘솔 초기 계정 생성 실패 |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana 기본 비밀번호(`admin`)로 노출 |
| `SLACK_WEBHOOK_URL_QUALITY` | 드리프트 경보 미발송 — 시연 중 알림 흐름 단절 |
| `DETECTOR_REVISION` | 워커 기동 시 `main` 수신 → 리비전 미고정, 점수 분포 언제든 변동 가능 |
| `EMBEDDING_REVISION` | 동일 — 임베딩 결과 재현 불가, 드리프트 탐지 신뢰성 저하 |

---

## GitHub Secrets 관리

운영 배포에 필요한 비밀값은 `.env`가 아닌 **GitHub Secrets**에서 관리한다.
CD 파이프라인이 서버 접속 시 Secrets에서 값을 읽어 SCP로 서버의 `.env`에 써넣는다 (ADR-021).

**등록 위치:** GitHub 저장소 → Settings → Secrets and variables → Actions

| GitHub Secret 이름 | 대응 변수 |
| --- | --- |
| `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` |
| `HF_TOKEN` | `HF_TOKEN` |
| `VULTR_SSH_KEY` | 서버 SSH 비밀키 전체 내용 (ADR-020) |
| `VULTR_SERVER_IP` | `VULTR_SERVER_IP` |
| `CONSOLE_SECRET_KEY` | `CONSOLE_SECRET_KEY` |
| `CONSOLE_ADMIN_PASSWORD` | `CONSOLE_ADMIN_PASSWORD` |
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` |
| `REDIS_PASSWORD` | `REDIS_PASSWORD` |
| `GF_SECURITY_ADMIN_PASSWORD` | `GF_SECURITY_ADMIN_PASSWORD` |
| `SLACK_WEBHOOK_URL_QUALITY` | `SLACK_WEBHOOK_URL_QUALITY` |
| `SLACK_WEBHOOK_URL_OPS` | `SLACK_WEBHOOK_URL_OPS` |
| `GHCR_TOKEN` | GHCR 이미지 Push·Pull용 GitHub PAT |

**배포 스위치:** CD의 서버 배포 잡은 저장소 Variables의 `DEPLOY_ENABLED`가 `true`일 때만 실행된다. 등록 위치는 같은 화면의 **Variables** 탭이다. 서버와 `VULTR_*` Secrets를 등록한 뒤 켠다(SP3).

---

## 메모

- `.env`는 절대 커밋하지 않는다. `.gitignore`에 이미 등록됨.
- `.env.example`에 새 변수를 추가할 때는 이 문서도 함께 업데이트한다.
- `AGENT_MAX_CALLS` · `AGENT_MAX_TOKENS` · `LLM_BUDGET_USD`는 정책 문서 8장과 항상 동기화한다. 코드 하드코딩 금지.
- 모델 리비전(`DETECTOR_REVISION`, `EMBEDDING_REVISION`)은 SP2 워커 구현 **전**에 반드시 채운다.
- 서버의 `.env` 파일 권한은 `chmod 600`으로 설정한다 (ADR-021).
- 정책 2.2의 설정 관계 불변식 4종(배치 대기 < 판정 창, 인시던트·알림 쿨다운 ≥ 판정 창, 점유 만료 > LLM 타임아웃)은 backend 기동 시 설정 검증에서 확인하고, 위반 시 기동을 중단한다.

---

end.