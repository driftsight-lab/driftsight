# AI 협업 안내

팀원 전용 문서로, Claude Code로 작업할 때 필요한 파일 구조·사용법·GitHub MCP 연결 방법을 다룬다.  
AI가 따르는 규칙은 저장소 루트 `CLAUDE.md`에 있다.

---

## 1. 파일 구조

| 파일 | 역할 |
| --- | --- |
| `CLAUDE.md` | Claude Code가 자동으로 읽는 AI 작업 규칙 원본 |
| `backend/CLAUDE.md` | backend 파트 기술 컨벤션 |
| `frontend/CLAUDE.md` | frontend 파트 기술 컨벤션 |
| `model/CLAUDE.md` | model 파트 기술 컨벤션 |
| `infra/CLAUDE.md` | infra 파트 기술 컨벤션 |
| `.mcp.json` | Claude Code GitHub MCP 서버 설정 |
| `docs/ai/README.md` | 이 문서 — 팀원용 사용 안내 |
| `docs/ai/prompts/` | 단계별 프롬프트 파일 |
| `docs/ai/review-checklist.md` | PR 리뷰 기준 |

- 워크플로우 규칙을 바꾸려면 루트 `CLAUDE.md`만 수정한다.
- 기술 컨벤션을 바꾸려면 해당 파트의 `CLAUDE.md`만 수정한다.
- `CLAUDE.md`는 토큰 사용량을 줄이기 위해 영어로 작성했다. 기준 문서 섹션 제목은 한국어 원문 그대로 가리킨다.
- AI 답변과 Issue·PR·커밋 메시지는 한국어로 작성한다.

---

## 2. 세션 시작

저장소 루트에서 Claude Code를 실행하고, 첫 메시지로 담당 파트와 이슈 번호를 알린다.

```bash
claude   # 저장소 루트에서 실행
```

**CLAUDE.md 로드 확인**

| 확인 방법 | 기대 결과 |
| --- | --- |
| `/memory` 입력 | `CLAUDE.md` 내용이 표시됨 |
| `/mcp` 입력 | `github` connected 표시 |

서브디렉토리(`backend/`, `frontend/`, `model/`, `infra/`)에서 작업할 때는 해당 디렉토리의 `CLAUDE.md`가 루트 파일에 추가로 로드된다.

**비밀값 처리 원칙**

- DB 계정·토큰·비밀번호가 포함된 명령은 Claude Code 터미널이 아닌 별도 PowerShell에서 직접 실행한다.
- Claude Code에 비밀값을 직접 입력하지 않는다.

**Stack PR 연결**

MCP로 base 브랜치 지정까지만 가능하다. `Create stack` / `Add to stack`은 GitHub 웹에서 직접 클릭한다.

---

## 3. GitHub MCP 연결

GitHub Issue·PR을 조회하고, 사용자 승인 후 등록할 수 있도록 GitHub MCP 서버를 연결한다.  
저장소의 `.mcp.json`을 공유하므로 **PAT 등록만 하면 된다. 추가 설정 없음.**

### 3.1 준비물

- Docker Desktop 설치 및 실행 (`docker version`으로 확인)
- `driftsight` 저장소 전용 Fine-grained PAT

### 3.2 PAT 발급

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token

| 항목 | 값 |
| --- | --- |
| Resource owner | `driftsight-lab` |
| Repository access | Only select repositories → `driftsight` |
| Expiration | 프로젝트 종료일 이전 |
| Contents | Read-only |
| Issues | Read and write |
| Pull requests | Read and write |
| Metadata | Read-only (자동) |

> `Contents`를 Read and write로 올리지 않는다. 올리면 AI가 GitHub에서 파일을 직접 수정하거나 push할 수 있다.  
> Resource owner는 본인 계정이 아닌 `driftsight-lab` 조직으로 설정한다. 조직이 Fine-grained PAT 승인을 요구하면 발급 후 관리자 승인을 받는다.

### 3.3 환경 변수 등록

토큰은 파일이 아닌 사용자 환경 변수 `GITHUB_PAT`로 등록한다.

**Windows (PowerShell)**

```powershell
setx GITHUB_PAT "발급한_토큰"
```

`setx`는 현재 터미널에 즉시 반영되지 않는다. 등록 후 **터미널(또는 IDE)을 완전히 종료하고 다시 실행**해야 적용된다.

```powershell
# 등록 확인 — 토큰 값을 직접 출력하지 않고 길이만 확인
($env:GITHUB_PAT).Length   # 90 이상이면 정상, 0이면 재시작 필요
```

**macOS / Linux (bash / zsh)**

```bash
echo 'export GITHUB_PAT="발급한_토큰"' >> ~/.zshrc   # 또는 ~/.bashrc
source ~/.zshrc
echo ${#GITHUB_PAT}   # 90 이상이면 정상
```

### 3.4 Claude Code 설정

추가 설정 없음. `.mcp.json`이 저장소에 포함되어 있다.

첫 실행 시 아래 순서로 화면이 뜬다.

1. **신뢰 폴더 확인** — "Yes, I trust this folder" 선택
2. **MCP 서버 허용** — "Use this and all future MCP servers in this project" 선택
3. **로그인** — `/login` 입력 후 "Claude account with subscription" 선택

로그인 없이는 Issue 조회 등 MCP 기능이 동작하지 않는다.

### 3.5 연결 확인

MCP 서버 이미지를 먼저 받는다. 이 단계를 건너뛰면 연결이 실패한다.

```bash
docker pull ghcr.io/github/github-mcp-server
```

Claude Code에서 `/mcp`를 입력해 `github` connected가 표시되는지 확인한다.  
이후 열려 있는 이슈 하나의 제목을 물어본다. 예: "이슈 #1 제목을 알려줘"

### 3.6 권한 범위

| 항목 | 제한 |
| --- | --- |
| MCP 툴셋 | `context,repos,issues,pull_requests`만 연결 |
| PAT | `Contents: Read-only`라 파일 수정·push 불가. Issue·PR·댓글 작성 가능 |
| 병합 | `main`, `develop` 브랜치 직접 push 금지. PR을 통해서만 머지 |

AI는 `CLAUDE.md` §0에 따라 사용자 승인 전에는 Issue·PR·댓글을 등록하지 않는다.

### 3.7 문제 해결

| 증상 | 확인 |
| --- | --- |
| `github` failed | Docker Desktop 실행 여부, `docker pull` 성공 여부 |
| 환경 변수 누락 경고 | `GITHUB_PAT` 등록 여부, 터미널 재시작 여부 |
| `($env:GITHUB_PAT).Length`가 0 | 터미널 재시작 재확인, `setx`를 관리자 권한 PowerShell로 재실행 |
| Git Bash에서 환경 변수 안 읽힘 | `export GITHUB_PAT=$(cmd //c echo %GITHUB_PAT%)`로 임시 적용 |
| Docker 명령을 찾을 수 없음 | Docker Desktop 실행 여부, PATH에 Docker 등록 여부 |
| 401 Bad credentials | 터미널에서 `($env:GITHUB_PAT).Length` 확인, 토큰 만료 여부 |

### 3.8 보안

- 토큰을 `.mcp.json`·`.env`·Issue·PR·스크린샷에 남기지 않는다.
- 노출이 의심되면 즉시 GitHub에서 토큰을 폐기하고 재발급한다. push된 경우에도 커밋 정리보다 폐기를 먼저 한다.

---

## 4. 단계별 프롬프트

AI에게 단계 이름으로 요청하면 `CLAUDE.md` §7에 따라 해당 프롬프트 파일을 읽고 진행한다.  
프롬프트 파일은 AI가 읽는 문서라 영어로 작성했고, AI의 답변과 출력 표는 한국어다.

### 파이프라인 흐름

```
기획: [00 세션 시작] → [10 계획] ──────────────────────────────→ [20 이슈 작성]
                             │                                           │
                   /grill-with-docs ──(Human gate)          (Human gate: 등록 승인)
                   /to-spec         ──(Human gate)
                   /to-tickets      ──(Human gate)
                             └ 계약 변경 필요 → 먼저 처리

구현: [30 구현] ──(Human gate: 커밋마다)
         └ src/interfaces/ 계약 충돌 → 즉시 중단·보고
      [40 자체 리뷰] ── review-checklist.md ── 미통과 → 30 복귀
      [50 PR 작성] ──(Human gate: Draft 등록 승인)

피드백: [40 리뷰 보조] ── 코멘트 초안 (사람이 직접 등록)
        [60 트러블슈팅] → 30 복귀 / 필요 시 50 업데이트
```

### 프롬프트 파일

| 파일 | 단계 | 출력 |
| --- | --- | --- |
| `00-session-start.md` | 세션 시작 | 세션 준비 확인 (담당·이슈·Stack 정보) |
| `10-plan.md` | /grill-with-docs · /to-spec · /to-tickets | 설계 질문 목록 · 확정 스펙 · 커밋 단위 표 |
| `20-issue-write.md` | 이슈 작성 (신규·수정) | Issue 본문 |
| `30-implement-backend.md` | backend 구현 | 커밋 |
| `30-implement-model.md` | model 구현 | 커밋 |
| `30-implement-ui.md` | frontend 구현 | 커밋 |
| `40-review.md` | 자체 리뷰 / 리뷰 보조 | 판정 결과 / 코멘트 초안 |
| `50-pr-write.md` | PR 작성 (신규·업데이트) | PR 본문 |
| `60-troubleshoot.md` | 트러블슈팅 | 수정 커밋 · PR 업데이트 내용 |

리뷰 기준은 `docs/ai/review-checklist.md`만 사용한다. 자체 리뷰와 팀 리뷰 모두 같은 기준을 쓴다.

### 사용 방법

| 단계 | 요청에 포함할 내용 |
| --- | --- |
| 세션 시작 | 담당 파트 (AI-SVC / AI-MDL), 이슈 #번호 |
| 계획·이슈 쪼개기 | 이슈 #번호 또는 작업 범위 |
| 이슈 작성 | 이슈 제목 또는 10단계 확정 항목 |
| 구현 (backend / model / frontend) | 이슈 #번호, Stack base 브랜치 (Stack인 경우) |
| 리뷰 | 자체 리뷰 또는 PR #번호 |
| PR 작성 | 이슈 #번호, base 브랜치 |
| 트러블슈팅 | 오류 메시지 전문 또는 리뷰 코멘트 |

### 주의사항

- 각 단계는 출력 후 사람의 승인을 기다린다. AI가 스스로 다음 단계로 넘어가지 않는다.
- 리뷰 기준은 `docs/ai/review-checklist.md` 하나만 쓴다.
- 프롬프트가 실제 작업과 맞지 않으면 개선 Issue를 만든다.

---

## 5. 참고 자료

- Claude Code 메모리 (`CLAUDE.md`): <https://docs.claude.com/en/docs/claude-code/memory>
- Claude Code MCP (`.mcp.json`): <https://docs.claude.com/en/docs/claude-code/mcp>
- GitHub MCP Server: <https://github.com/github/github-mcp-server>

---

end.