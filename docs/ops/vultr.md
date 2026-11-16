# Vultr 클라우드 운영 매뉴얼

> **최종 수정일**: 2026-10-31  
> **담당**: AI-SVC

---

## 1. 계정 및 사전 준비

### 1.1 계정

- Vultr 계정: 팀 공유 계정 사용 (이메일 주소는 팀 채널 고정 메시지 확인)
- 결제 수단 등록 후 $40 이상 선불 크레딧이 있는지 확인한다.

### 1.2 로컬에 필요한 도구

**macOS / Linux**

```bash
# SSH 클라이언트 (기본 포함)
ssh -V

# Vultr CLI (선택 — 없어도 무방)
brew install vultr-cli        # macOS
```

**Windows (Git Bash)**

```bash
# SSH 클라이언트 — Git for Windows 설치 시 Git Bash에 포함
ssh -V

# Vultr CLI (선택)
# winget install Vultr.VultrCLI   ← PowerShell에서 실행
# https://github.com/vultr/vultr-cli
```

> 이하 모든 명령어는 **Git Bash** 기준이다. PowerShell·CMD에서는 경로 구분자(`/` → `\`)와 일부 명령어가 다를 수 있다.
> 

### 1.3 SSH 키 생성 (최초 1회)

```bash
# 팀용 SSH 키쌍 생성 (macOS·Linux·Windows Git Bash 동일)
ssh-keygen -t ed25519 -C "aisv-team17" -f ~/.ssh/aisv_team17

# 공개키 출력 — Vultr에 등록할 내용
cat ~/.ssh/aisv_team17.pub
```

> **Windows 키 파일 경로**: `C:\Users\<사용자명>\.ssh\aisv_team17`
Git Bash에서는 `~/.ssh/aisv_team17`로 동일하게 접근 가능하다.
> 

생성된 **공개키(`aisv_team17.pub`)** 를 Vultr에 등록한다 (아래 3.2 참고).

**비밀키(`aisv_team17`)는 절대 공유하지 않는다.** GitHub Secret(`VULTR_SSH_KEY`)에만 넣는다.

---

## 2. 서버 사양 및 선택 이유

| 항목 | 선택 | 근거 |
| --- | --- | --- |
| 위치 | Seoul (icn) | 국내 접속 지연 최소화, 학교 지원 조건 충족 (ADR-014) |
| 플랜 | Cloud Compute — High Performance (vhp-4c-8gb) | 4 vCPU / 8 GB RAM / 128 GB NVMe SSD |
| OS | Ubuntu 24.04 LTS | Docker 공식 지원, 장기 지원 |
| 월 정가 | ~$48/월 (시간당 $0.064) | 한 달 내내 켜둘 경우 |
| 크레딧 | $40 선불 (11/1~12/13, 약 625시간 가동 가능) | Destroy 전략 적용 시 $20~30 이내 예상 |

**사양 선택 근거 (ADR-014):**

- FastAPI 서비스 6개 + PostgreSQL + OTel Collector + Prometheus + Grafana + Next.js 동시 구동
- 컨테이너별 `mem_limit` 합계 약 6.75 GB → 8 GB RAM 필요
- ONNX 추론 시 CPU 스파이크가 발생하므로 버스트 제한이 없는 High Performance 플랜 선택
- AMD EPYC 기반 NVMe로 동급 HDD 플랜(vc2-4c-8gb) 대비 약 2배 처리량

---

## 3. 서버 생성

### 3.1 콘솔에서 생성

1. my.vultr.com 로그인 → **Deploy +** 클릭
2. **Choose Server**: Cloud Compute → **High Performance**
3. **Server Location**: Seoul (ICN)
4. **Server Image**: Ubuntu 24.04 LTS x64
5. **Server Size**: 4 vCPU / 8 GB RAM / 128 GB NVMe SSD 선택
6. **Additional Features**:
    - ☑ **Enable IPv6** (선택)
    - ☑ **Enable Backups** — 월 $4.80, 활성화 권장
7. **SSH Keys**: 아래 3.2에서 등록한 키 선택
8. **Server Hostname**: `aisv-team17-prod`
9. **Deploy Now** 클릭

생성 완료까지 약 60~90초 소요. **퍼블릭 IP**를 팀 채널 고정 메시지에 기록한다.
실제 IP·비밀값은 `비밀번호.md`(git 미포함)에 보관한다.

### 3.2 SSH 키 Vultr 등록

1. **Account → SSH Keys → Add SSH Key**
2. 이름: `aisv-team17`
3. 공개키 내용 붙여넣기 (`cat ~/.ssh/aisv_team17.pub` 출력값)
4. **Add SSH Key** 저장

### 3.3 접속 확인

```bash
# macOS · Linux · Windows Git Bash 동일
ssh -i ~/.ssh/aisv_team17 root@<SERVER_IP>
```

> **Windows 최초 접속 시** `~/.ssh/aisv_team17` 파일 권한 오류가 날 수 있다.
Git Bash에서 아래 명령으로 권한을 수정한다.
> 
> 
> ```bash
> chmod 600 ~/.ssh/aisv_team17
> ```
> 

---

## 4. 방화벽 설정

> Vultr 방화벽 그룹으로 불필요한 포트를 차단한다.
> 

### 4.1 방화벽 그룹 생성

1. **Network → Firewall → Add Firewall Group**
2. 이름: `aisv-team17-fw`

### 4.2 인바운드 규칙

| 프로토콜 | 포트 | 소스 | 용도 |
| --- | --- | --- | --- |
| TCP | 22 | 팀원 IP | SSH (전체 공개 금지) |
| TCP | 3000 | `0.0.0.0/0` | 관제 콘솔 UI (Next.js) |
| TCP | 3001 | `0.0.0.0/0` | Grafana |
| TCP | 4318 | `0.0.0.0/0` | OTel Collector OTLP HTTP |
| TCP | 8000 | `0.0.0.0/0` | RAG 서비스 |

> **현재 미구현**: Nginx 리버스 프록시는 이번 범위 밖이다.
추후 Nginx 추가 시 3000·3001·8000·4318을 내부 전용으로 변경하고 80/443만 공개한다.
> 

> **내부 서비스 포트(8001~8002, 5432, 6379, 9090 등)는 외부 공개하지 않는다.**
> 

### 4.3 방화벽 서버 연결

**Servers** → 생성한 서버 → **Firewall** → `aisv-team17-fw` 선택 → **Update Firewall Group**

---

## 5. 서버 초기 세팅

> SSH 접속 후 아래 명령을 순서대로 실행한다.
> 

### 5.1 시스템 업데이트

```bash
apt-get update && apt-get upgrade -y
apt-get install -y curl git vim ufw
```

### 5.2 UFW 방화벽 (OS 레벨 이중 보호)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 3000/tcp
ufw allow 3001/tcp
ufw allow 4318/tcp
ufw allow 8000/tcp
ufw --force enable
ufw status verbose
```

### 5.3 Docker 설치

```bash
curl -fsSL https://get.docker.com | sh

# 시작 시 자동 실행
systemctl enable docker
systemctl start docker

# 설치 확인
docker version
docker compose version
```

### 5.4 작업 디렉토리 생성

```bash
mkdir -p /opt/aisv-team17
cd /opt/aisv-team17
```

### 5.5 환경 변수 파일 생성

```bash
# .env 파일은 cd.yml이 GitHub Secrets에서 SCP로 주입 (ADR-021)
# 최초 수동 배포 시 직접 작성
vim .env
chmod 600 .env   # 소유자만 읽기·쓰기
```

### 5.6 Swap 설정 (ONNX 추론 메모리 스파이크 대비)

```bash
# 2 GB Swap 파일 생성
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# 재부팅 후에도 유지
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 확인
free -h
```

---

## 6. Docker 및 프로젝트 배포

### 6.1 이미지 빌드 및 최초 배포

```bash
cd /opt/aisv-team17

# 저장소 clone (최초 1회)
git clone git clone https://github.com/driftsight-lab/driftsight.git .

# 환경 변수 설정
cp .env.example .env
vim .env        # 비밀값 입력
chmod 600 .env

# GHCR 로그인 (최초 1회)
echo "<GHCR_TOKEN>" | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin

# 전체 서비스 기동
docker compose pull
docker compose up -d

# 상태 확인
docker compose ps
docker compose logs -f
```

### 6.2 DB 마이그레이션

```bash
# Alembic 마이그레이션 실행 (서비스 기동 후)
docker compose exec console alembic upgrade head
```

### 6.3 ONNX 모델 다운로드

```bash
# 워커 컨테이너에서 모델 Pull (최초 1회 또는 모델 업데이트 시)
# SP2: LettuceDetect 기준선 모델 사용 (ADR-027)
# SP3: 자체 학습 모델로 교체 예정 (aisv-team17/halludetect-onnx)
docker compose exec worker python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='KRLabsOrg/lettucedect-base-modernbert-en-v1',
    local_dir='/app/models'
)
"
```

### 6.4 개별 서비스 로그 확인

```bash
docker compose logs -f rag
docker compose logs -f worker
docker compose logs -f ingest
```

### 6.5 CD 자동 배포 (GitHub Actions)

`main` 브랜치에 push하면 `cd.yml`이 자동으로:

1. Docker 이미지 빌드 → GHCR 푸시 (SHA 태그, ADR-019)
2. GitHub Secrets → 서버 `.env` SCP 주입 (ADR-021)
3. SSH Deploy Key로 서버 접속 → `docker compose pull && docker compose up -d` (ADR-020)
4. `alembic upgrade head` 자동 실행
5. `docker image prune -f`로 디스크 정리

**수동 롤백이 필요할 때:**

```bash
cd /opt/aisv-team17

# 실행 중인 서비스 확인
docker compose ps

# 특정 SHA 태그 이미지로 롤백
# docker-compose.yml의 image 태그를 이전 버전으로 수정 후
docker compose pull
docker compose up -d

# 이전 이미지가 로컬에 있을 경우 pull 없이 바로 기동
docker compose up -d --no-pull
```

---

## 7. 비용 통제

### 7.1 Destroy 전략

> Vultr에서 서버를 **중지(Stop)**해도 인스턴스 요금은 계속 청구된다.
**완전 삭제(Destroy)** 후 재생성해야 비용이 멈춘다.
8주 프로젝트 특성상 **필요할 때만 생성, 미사용 시 Destroy** 전략을 권장한다.
> 

Destroy 전 반드시 DB 백업 (8. 서버 재생성 절차 참고).

### 7.2 디스크 사용량 확인

```bash
df -h                           # 전체 디스크
docker system df                # Docker 사용량
docker image prune -f           # 댕글링 이미지 삭제
docker volume prune -f          # 미사용 볼륨 삭제 (주의: 데이터 손실)
```

### 7.3 예산

| 항목 | 내용 |
| --- | --- |
| 크레딧 | $40 선불 (11/1~12/13, 약 43일) |
| 단가 | 시간당 $0.064 (vhp-4c-8gb, Seoul icn) |
| 최대 가동 가능 시간 | 약 625시간 ($40 ÷ $0.064) |
| 자동 백업 (선택) | ~$4.80/월 |
| 대역폭 | 3 TB 포함, 초과 시 $0.01/GB |
| **예상 실사용** | **$20~30** (Destroy 전략, 수업·시연 시간만 가동) |

> 한 달 내내 켜두면 ~$53/월이므로 크레딧 초과. Destroy 전략이 필수다.
> 

---

## 8. 서버 재생성 절차

> 프로젝트 종료 후 또는 서버를 완전히 초기화해야 할 때.
> 

### 8.1 데이터 백업

```bash
# PostgreSQL 백업 (서버에서 실행)
docker compose exec postgres pg_dump -U aisv aisv > backup_$(date +%Y%m%d).sql

# 백업 파일 로컬로 복사 (로컬 Git Bash에서 실행)
scp -i ~/.ssh/aisv_team17 root@<SERVER_IP>:/opt/aisv-team17/backup_*.sql ./
```

> **Windows Git Bash**: `$(date +%Y%m%d)` 문법이 동작하지 않을 수 있다. 서버(Ubuntu)에서 직접 실행하므로 문제없다. scp는 Git Bash에서 동일하게 동작한다.
> 

### 8.2 서버 삭제

1. my.vultr.com → **Products → Compute**
2. 서버 선택 → **···** → **Destroy Server**
3. 체크박스 확인 후 **Destroy** 클릭

### 8.3 재생성

위 3. 서버 생성부터 6. Docker 및 프로젝트 배포까지 순서대로 반복한다.

DB 복원이 필요하면:

```bash
docker compose exec -T postgres psql -U aisv aisv < backup_20261102.sql
```

---

## 참고

*Vultr 공식 문서: https://docs.vultr.com*

---

end.