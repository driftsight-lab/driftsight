# Docker 컨테이너 운영 매뉴얼

> **최종 수정일**: 2026-11-02   
> **담당**: AI-SVC

---

## 1. 컨테이너 구성

모든 Python 서비스는 `backend/`의 **단일 이미지**를 공유하며, `docker-compose.yml`에서 `command`만 달리한다.

| 서비스명 | 역할 | 내부 포트 | 외부 공개 | 로컬 포트 (override) |
| --- | --- | --- | --- | --- |
| `postgres` | PostgreSQL 16 + pgvector | 5432 | ❌ | 5433 |
| `redis` | Redis 7 — 세션·캐시 | 6379 | ❌ | 6381 |
| `otel-collector` | OTel Collector — OTLP HTTP 수신 | 4318 | ✅ | 4319 |
| `rag` | RAG 서비스 (FastAPI) | 8000 | ✅ | 8000 |
| `ingest` | Ingest API (FastAPI) | 8001 | ❌ | 8001 |
| `worker` | 비동기 검사 워커 | — | ❌ | — |
| `drift` | 드리프트 판정 모니터 | — | ❌ | — |
| `agent` | 원인 분석 에이전트 | — | ❌ | — |
| `console` | 관제 콘솔 백엔드 (FastAPI) | 8002 | ❌ | 8002 |
| `frontend` | Next.js 관제 콘솔 UI | 3000 | ✅ | 3000 |
| `prometheus` | 메트릭 수집 | 9090 | ❌ | 9091 |
| `grafana` | 대시보드 | 3000→3001 | ✅ | 3001 |
- `redis` , `otel-collector` , `prometheus`
    - **로컬 포트 충돌** 대응으로 기본값에서 변경됨. `.env`에서 조정 가능.
- `ingest` , `console`
    - **`docker-compose.override.yml`** 에서만 로컬 포트 노출 (운영에서는 내부 전용).
    - `worker`·`drift`·`agent`는 HTTP 포트가 없는 백그라운드 프로세스다.

---

## 2. 메모리 할당 기준

`docker-compose.yml`에서 `mem_limit`으로 상한을 설정한다. 서버 총 RAM **8 GB** (vhp-4c-8gb, ADR-014):

| 컨테이너 | mem_limit | 비고 |
| --- | --- | --- |
| `postgres` | 2048m | pgvector 인덱스 상주 고려 |
| `redis` | 256m | `maxmemory 200mb` 설정 권장 |
| `otel-collector` | 256m | ADR-013 명시값 |
| `rag` | 512m | 임베딩 모델 로드 시 스파이크 |
| `ingest` | 256m |  |
| `worker` | 1536m | ONNX 모델 + sentence-transformers 적재 고려 |
| `drift` | 256m | APScheduler 상주 |
| `agent` | 512m | LLM 호출 버퍼 |
| `console` | 256m |  |
| `frontend` | 256m | Next.js standalone |
| `prometheus` | 512m | 15일 보존 기준 |
| `grafana` | 256m |  |
| **합계** | **~6,912m (≈ 6.75 GB)** | 8 GB 중 84% — Swap 2 GB로 스파이크 흡수 |

---

## 3. 로컬 개발 환경 실행

### 3.1 사전 준비

```bash
# .env 파일 생성
cp .env.example .env

# 필수 값 입력 (비밀번호.md 참고)
# POSTGRES_PASSWORD, REDIS_PASSWORD, ANTHROPIC_API_KEY 등
vim .env       # macOS·Linux
notepad .env   # Windows
```

### 3.2 전체 스택 기동

```bash
# 이미지 빌드 + 백그라운드 실행
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build

# 상태 확인
docker compose ps

# 전체 로그 실시간 확인
docker compose logs -f
```

### 3.3 DB 마이그레이션 (최초 실행 또는 스키마 변경 시)

```bash
docker compose exec console alembic upgrade head
```

### 3.4 ONNX 모델 다운로드 (최초 실행 시)

```bash
# SP2 기준: LettuceDetect 기준선 모델 (ADR-027)
# SP3에서 자체 학습 모델(aisv-team17/halludetect-onnx)로 교체 예정
docker compose exec worker python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='KRLabsOrg/lettucedect-base-modernbert-en-v1',
    local_dir='/app/models'
)
print('모델 다운로드 완료')
"
```

### 3.5 서비스 접근 URL (로컬)

| 서비스 | URL | 비고 |
| --- | --- | --- |
| 관제 콘솔 (UI) | http://localhost:3000 | — |
| RAG API 문서 | http://localhost:8000/docs | — |
| Ingest API 문서 | http://localhost:8001/docs | override.yml 포트 노출 시 |
| 관제 콘솔 백엔드 | http://localhost:8002/docs | override.yml 포트 노출 시 |
| Prometheus | http://localhost:9091 | 로컬 포트 충돌로 9091 사용 |
| Grafana | http://localhost:3001 | admin / `.env`의 `GF_SECURITY_ADMIN_PASSWORD` |

---

## 4. 운영 환경 실행

운영 서버에서는 `docker-compose.override.yml`을 사용하지 않는다.

```bash
cd /opt/aisv-team17

# .env 파일 확인 (cd.yml이 GitHub Secrets에서 SCP로 주입)
ls -la .env
chmod 600 .env

# GHCR 로그인 (최초 1회 또는 토큰 갱신 시)
echo "${GHCR_TOKEN}" | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin

# 최신 이미지 Pull
docker compose pull

# 서비스 기동
docker compose up -d --remove-orphans

# DB 마이그레이션
docker compose exec -T console alembic upgrade head

# 댕글링 이미지 정리
docker image prune -f
```

---

## 5. 이미지 빌드

### 5.1 로컬 빌드

```bash
# backend 이미지만 재빌드
docker compose build backend

# 특정 서비스만 재빌드 후 재시작
docker compose up -d --build worker
```

### 5.2 GHCR 푸시 (cd.yml에서 자동 처리)

```bash
# GitHub Container Registry 로그인
echo "${GHCR_TOKEN}" | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin

# 이미지 빌드 & 태그 & 푸시 (SHA 태그 방식, ADR-019)
IMAGE_TAG=sha-$(git rev-parse --short HEAD)

docker build -t ghcr.io/driftsight-lab/driftsight/backend:${IMAGE_TAG} ./backend
docker push ghcr.io/driftsight-lab/driftsight/backend:${IMAGE_TAG}

docker build -t ghcr.io/driftsight-lab/driftsight/frontend:${IMAGE_TAG} ./frontend
docker push ghcr.io/driftsight-lab/driftsight/frontend:${IMAGE_TAG}
```

---

## 6. 로그 및 디버깅

### 6.1 서비스별 로그

```bash
# 특정 서비스 로그 실시간 확인
docker compose logs -f rag
docker compose logs -f worker
docker compose logs -f ingest
docker compose logs -f drift
docker compose logs -f agent
docker compose logs -f console
docker compose logs -f postgres
docker compose logs -f otel-collector

# 마지막 100줄 확인
docker compose logs --tail=100 worker
```

### 6.2 컨테이너 쉘 진입

```bash
# Python 서비스 쉘
docker compose exec worker bash

# PostgreSQL 콘솔
docker compose exec postgres psql -U aisv aisv

# Redis 확인
docker compose exec redis redis-cli -a ${REDIS_PASSWORD} ping
docker compose exec redis redis-cli -a ${REDIS_PASSWORD} info memory
```

### 6.3 OTel 스팬 수신 확인

```bash
# Collector가 스팬을 받고 있는지 확인
docker compose logs -f otel-collector

# Ingest API 수신 확인
docker compose logs -f ingest | grep "trace"
```

### 6.4 Worker 검사 작업 대기열 확인

```bash
docker compose exec postgres psql -U aisv aisv -c "
  SELECT status, COUNT(*)
  FROM eval_jobs
  GROUP BY status
  ORDER BY status;
"
```

### 6.5 메모리 사용량 확인

```bash
# 전체 컨테이너 실시간 리소스
docker stats

# 특정 컨테이너 상세 (worker mem_limit 초과 여부)
docker stats aisv-worker-1 --no-stream

# Swap 사용량 (서버에서)
free -h
```

---

## 7. 데이터 초기화

> **주의:** 아래 명령은 볼륨을 삭제한다. 복구 불가.
> 

```bash
# 컨테이너만 종료 (데이터 유지)
docker compose down

# 컨테이너 + 볼륨 삭제 (DB 데이터 포함)
docker compose down --volumes

# 특정 볼륨만 삭제 (DB만 초기화)
docker compose down
docker volume rm aisv_postgres_data
docker compose up -d
docker compose exec console alembic upgrade head
```

### 7.1 DB 백업 및 복원

```bash
# 백업 (서버에서 실행)
docker compose exec postgres pg_dump -U aisv aisv > backup_$(date +%Y%m%d_%H%M%S).sql

# 복원
docker compose exec -T postgres psql -U aisv aisv < backup_20261102_120000.sql
```

---

## 8. 자주 쓰는 명령어

```bash
# 서비스 상태 한 눈에 확인
docker compose ps

# 특정 서비스만 재시작
docker compose restart worker

# worker만 2개로 스케일 아웃 (실험용)
docker compose up -d --scale worker=2

# 전체 Docker 사용 디스크
docker system df

# 미사용 리소스 정리 (볼륨 제외)
docker system prune -f

# 이미지만 정리 (전체)
docker image prune -a -f

# 컨테이너 IP 확인
docker inspect -f '{{.Name}} - {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose ps -q)
```

---

## 메모

- `docker-compose.yml` 변경 시 반드시 AI-SVC 승인 후 PR 병합 (CODEOWNERS 규칙)
- 로컬 포트 충돌 시 `.env`에서 `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT` 값 변경

---

end.