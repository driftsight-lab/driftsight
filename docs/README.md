# AISV-Team17 문서

- 프로젝트 설계·운영·실험 문서는 이 디렉터리에서 관리합니다.
- 새 자료는 아래 분류에 맞춰 저장하고 문서 목록에 링크를 추가합니다.

---

## 문서 목록

| 분류 | 문서 | 내용 |
|---|---|---|
| **기획** | [기획서](planning/scope.md) | 서비스 개요·MVP 범위·스프린트 일정·예산·리스크 |
| **기획** | UI 목업 | 관제 콘솔 7개 화면 목업·목업과 명세의 차이 |
| **아키텍처** | [다이어그램](architecture/diagrams.md) | 시스템 구성도·CI/CD 파이프라인·컨테이너 구성도 |
| **명세** | [SDD](specs/SDD.md) | 기능 요구사항·비기능 요구사항·설계 방어 포인트 |
| **명세** | [테스트 계획](specs/test-plan.md) | 단위·통합·인수 테스트 시나리오·CI/CD 검증 |
| **명세** | [정책](specs/policies.md) | 접근 권한·TTL·불변식·보안·알림 정책 |
| **명세** | [ERD](specs/erd.md) | DB 스키마·테이블 명세·인덱스·DDL |
| **명세** | [API 명세서](specs/api.md) | REST API 엔드포인트·요청·응답·에러 코드 |
| **명세** | [텔레메트리](specs/telemetry.md) | OTel 스팬 이름·속성 표·메트릭 정의 |
| **명세** | [인터페이스 계약](specs/interfaces.md) | Detector·DriftDetector 계약 (AI-SVC ↔ AI-MDL) |
| **운영** | [Vultr 클라우드](ops/vultr.md) | 서버 생성·방화벽·SSH·비용 절차 |
| **운영** | [Docker 운영](ops/docker.md) | 컨테이너 구성·mem_limit·로컬 실행 명령 |
| **운영** | [환경 변수 가이드](ops/env-setup.md) | .env.example 설명·섹션별 가이드·GitHub Secrets |
| **운영** | [모델 레지스트리](ops/model-registry.md) | HuggingFace Hub 업로드·리비전 고정·서빙 절차 |
| **운영** | [런북](ops/runbook.md) | 배포·롤백·장애 대응·서버 Destroy 규칙 |
| **실험** | [실험 프로토콜](experiments/protocol.md) | 과제 A~D 지표 정의·계산식·데이터 분할·시드 규칙 |
| **실험** | [데이터 관리](experiments/data.md) | RAGTruth·MT-Bench 다운로드·전처리·라이선스 |
| **실험** | [주입 시나리오 목록](experiments/injection-scenarios.md) | SCN-001~005 개요·공통 규칙 |
| **실험** | [SCN-001: 프롬프트 간결화](experiments/scenarios/SCN-001-prompt-simplification.md) | 시나리오 상세 |
| **실험** | [SCN-002: 생성 모델 교체](experiments/scenarios/SCN-002-model-replacement.md) | 시나리오 상세 |
| **실험** | [SCN-003: 검색 문서 수 축소](experiments/scenarios/SCN-003-retrieval-doc-reduction.md) | 시나리오 상세 |
| **실험** | [SCN-004: 청크 크기 변경](experiments/scenarios/SCN-004-chunk-size-change.md) | 시나리오 상세 |
| **실험** | [SCN-005: 검색 인덱스 손상](experiments/scenarios/SCN-005-index-corruption.md) | 시나리오 상세 |
| **템플릿** | [ADR 템플릿](adr/0000-adr-template.md) | 새 ADR 작성 시 복사해서 사용 |
| **템플릿** | [API 명세 템플릿](specs/template/api-template.md) | 새 엔드포인트 추가 시 복사해서 사용 |
| **템플릿** | [ERD 템플릿](specs/template/erd-template.md) | 새 테이블 추가 시 복사해서 사용 |
| **템플릿** | [인터페이스 템플릿](specs/template/interfaces-template.md) | 새 인터페이스 계약 추가 시 복사해서 사용 |
| **템플릿** | [시나리오 템플릿](experiments/scenarios/SCN-000-template.md) | 새 주입 시나리오 추가 시 복사해서 사용 |
| **ADR** | [ADR 목록](adr/) | 기술 결정 기록 0000~0029 |
| **AI 협업** | AI 협업 안내 | AI 도구 설정·세션 시작·GitHub MCP 연결·단계별 프롬프트 |

---

## 디렉터리 구분

| 경로 | 저장할 자료 |
|---|---|
| `planning/` | 기획서·개발 일정·스프린트 계획 |
| `architecture/` | 시스템 구성도·서비스 간 다이어그램 |
| `specs/` | API·ERD·인터페이스·정책·텔레메트리·테스트 계획 |
| `specs/template/` | 명세 작성 템플릿 — 복사해서 사용, 직접 수정 금지 |
| `experiments/scenarios/` | SCN별 시나리오 상세 파일 — `SCN-000-template.md` 포함 |
| `ops/` | 서버·Docker·환경 변수·모델·런북 등 운영 문서 |
| `experiments/` | 실험 프로토콜·데이터·주입 시나리오 목록 |
| `adr/` | Architecture Decision Record — `0000-adr-template.md` 포함 |
| `ai/` | AI 협업 안내·MCP 설정·리뷰 체크리스트·단계별 프롬프트 |

---

## 작성 규칙

- 폴더는 실제 자료를 추가할 때 만든다. 빈 폴더나 보존용 파일을 미리 만들지 않는다.
- 문서 파일명은 영문 소문자와 하이픈을 사용한다. 예: `env-setup.md`, `model-registry.md`
- 저장소 안의 문서와 이미지는 상대 경로로 연결한다. 예: `[런북](ops/runbook.md)`
- 자료를 옮기거나 파일명을 바꾸면 이 목록과 해당 자료를 참조하는 링크도 함께 수정한다.
- 같은 내용을 여러 곳에 복사하지 않고 해당 문서로 연결한다.
- 비밀값이 있는 자료(실제 `.env`, `비밀번호.md` 등)는 저장소에 추가하지 않는다.

---

## ADR 작성 규칙

- 새 ADR은 `adr/0000-adr-template.md`를 복사해 번호를 이어서 만든다.
- 파일명: `{번호4자리}-{영문-슬러그}.md` 예: `0030-new-decision.md`
- 결정이 바뀌면 새 ADR을 작성하고 기존 ADR 상태를 `대체됨 (→ NNNN)`으로 변경한다. 기존 파일은 삭제하지 않는다.

---

## 주입 시나리오 추가 규칙

- 새 시나리오는 `experiments/scenarios/SCN-000-template.md`를 복사해 번호를 이어서 만든다.
- 파일명: `SCN-{번호3자리}-{영문-슬러그}.md`
- 추가 후 `experiments/injection-scenarios.md` 목록과 이 README 문서 목록도 함께 갱신한다.

---

## AI 협업 안내 

AI 협업 규칙과 단계별 프롬프트는 `docs/ai/`에서 관리합니다.

| 파일 | 내용 |
|---|---|
| `ai/README.md` | AI 도구별 설정 파일·세션 시작·GitHub MCP 연결(3절)·단계별 프롬프트 사용법(4절) |
| `ai/review-checklist.md` | PR 리뷰 체크리스트·AI 리뷰 요청 템플릿 |
| `ai/prompts/` | 설계·구현·리뷰 단계별 프롬프트 모음 |

---

end.