# 관제 콘솔 UI 목업

- 관제 콘솔 화면의 **레이아웃 기준**이다. 데이터 구조·동작의 기준은 아니다.
- 구현 절차는 `docs/ai/prompts/30-implement-ui.md`를 따른다.

---

## 공통 규칙

- 목업의 수치·날짜·건수는 모두 예시다. 코드에 하드코딩하지 않는다.
- 데이터 구조와 필드의 기준은 [`docs/specs/api.md`](../specs/api.md)다. 화면별 호출 API는 api.md 부록 D(화면–API 대응표)를 본다.
- 목업과 ADR·명세가 다르면 **ADR·명세를 따르고**, 차이는 아래 표에 추가한다.
- 목업에만 있는 입력 항목·필드는 api.md에 반영되기 전에는 구현하지 않는다. 필요하면 문서 변경 이슈를 먼저 만든다.
- 콘솔 UI 문구는 한국어, 질문·응답·문서 등 감시 대상 콘텐츠는 영어다(ADR-016). 목업 속 한국어 질문·응답은 설명용이다.

---

## 화면 목록

| # | 화면 | 목업 | 담당 | 시점 | 관련 ADR |
| --- | --- | --- | --- | --- | --- |
| 1 | 품질 관제 대시보드 | [01-dashboard.png](01-dashboard.png) | `AI-SVC` | SP2 기본 → SP3 | ADR-008, ADR-029 |
| 2 | 요청 트레이스 상세 | [02-trace.png](02-trace.png) | `AI-SVC` | SP2 | ADR-006, ADR-024, ADR-027 |
| 3 | 버전별 A/B 비교 | [03-ab-compare.png](03-ab-compare.png) | `AI-MDL` | SP3 | ADR-005 |
| 4 | 인시던트 상세 | [04-incident.png](04-incident.png) | `AI-SVC` | SP3 | ADR-007 |
| 5 | 채점자 신뢰도 | [05-judge-reliability.png](05-judge-reliability.png) | `AI-MDL` | SP2 | ADR-015 |
| 6 | 2단 검사 라우팅 정책 | [06-routing-policy.png](06-routing-policy.png) | `AI-MDL` | SP3 | ADR-006 |
| 7 | 알림 설정 | [07-alert-settings.png](07-alert-settings.png) | `AI-SVC` | SP3 (권장) | ADR-011 |

- 로그인 화면은 목업이 없다. 기획서 3.2와 api.md 1장을 기준으로 한다.

---

## 목업과 명세의 차이 (명세 우선)

| # | 화면 | 목업 | 기준 | 근거 |
| --- | --- | --- | --- | --- |
| U-1 | 대시보드 | 비용·지연 패널을 콘솔 차트로 그림 | Grafana 패널 임베드(읽기 전용) | ADR-008 |
| U-2 | 인시던트·트레이스 | 원인 후보 "top-k 5 → 3", 트레이스 메타 "top-k 3" | `top_k: 5 → 2` (대시보드 알림 목업과 일치) | SCN-003 |
| U-3 | 인시던트 | 에이전트 도구 `get_version_history`, `query_traces`, `compare_scores`, `get_judge_results` | `list_version_changes`, `search_traces`, `compare_versions`, `get_judge_feedback`, `get_quality_timeseries` | api.md 11.1 |
| U-4 | 알림 설정 | 규칙 4종(점수 하한·환각 비율·일일 비용·평균 지연), 지속 시간, 감지 방식 선택 | `scoreThreshold`, `costThresholdUsd`, `cooldownMinutes`만 저장 | api.md 7.2 |
| U-5 | 트레이스·A/B | 모델명 `model-L`, 채점 모델 `Claude` | `configs/` 버전 식별자와 실제 모델 등급 표기 | ADR-005, ADR-015 |
| U-6 | 전 화면 | 서비스명 "사내 문서 QA 봇", 한국어 질문·응답 | 영어 RAG 서비스·코퍼스 | ADR-012, ADR-016 |

- U-4의 감지 방식 3종(고정 임계값·통계 검정·임베딩 거리)은 `DriftDetector` 구현 3종(ADR-029)에 대응한다. 설정 저장 대상으로 만들지는 api.md 변경 이슈에서 결정한다.

---

end.