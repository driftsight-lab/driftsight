# 주입 시나리오 명세 v1.0

> **최종 수정**: 2026-10-26

---

## 1. 개요

- **목적**: 품질 저하를 **의도적으로 주입**하여 드리프트 탐지(과제 C)와 원인 변경 지목(과제 D)의 성능을 측정할 수 있는 정답 라벨을 만든다. 관측 문제에는 원래 정답이 없으므로, **정답을 우리가 만들어 넣는 문제로 바꾼다**(카오스 엔지니어링 원리, ADR-026).
- **시나리오 수**: **6개** — 주입 5개(`label: 1`) + 정상 대조 1개(`label: 0`)
- **사용 실험**: 과제 C(드리프트 탐지 방식 비교), 과제 D(원인 변경 지목 정확도). 과제 A·B는 RAGTruth·MT-Bench를 쓴다.

### 1.1 이 시나리오가 실험에 쓰이는 흐름

1. `POST /api/v1/injections`로 회차를 실행한다. `scenarioId`는 `SCN-{3자리}` 형식이다.
2. 트래픽 생성기가 고정 질문 집합을 재생하고, 정해진 시점에 설정이 교체된다.
3. 교체는 `version_changes`에 `source='injection'`으로 기록되고, `injection_events`가 그 행을 가리킨다. **이 연결이 곧 정답 라벨이다**(erd.md 5장).
4. Drift Monitor가 저하를 탐지하면 인시던트가 생기고 에이전트가 원인을 지목한다.
5. `incidents.top1_version_change_id`와 `injection_events.version_change_id`(디코이 제외)를 조인해 Top-1 정확도를 자동 계산한다.

### 1.2 템플릿과 이 프로젝트의 층위 차이

이 프로젝트의 주입은 **운영 설정을 바꿔 품질이 저하되게 만드는 회차 단위 주입**이다.

| 구분 | 레코드 단위 주입(원형 템플릿) | **이 프로젝트 (회차 단위)** |
| --- | --- | --- |
| 주입 대상 | 개별 응답 텍스트 | 프롬프트·모델·검색 설정 |
| 정답 라벨 | "이 응답에 환각이 있다" | "이 **변경**이 품질 저하의 원인이다" |
| 산출물 | 평가용 레코드 집합 | 90분 트레이스 시계열 + 변경 이력 |
| 평가 지표 | 탐지 정밀도·재현율 | 탐지율·탐지 지연·오탐 횟수·Top-1/Top-3 정확도 |

---

## 2. 실제 사고 사례

각 시나리오의 현실 근거가 되는 공개 사고 사례다.

| ID | 사례 | 요지 |
| --- | --- | --- |
| **R1** | Anthropic, 2025년 8~9월 | 인프라 결함 3건이 겹쳐 Claude 응답 품질이 간헐적으로 저하됨. ① 일부 Sonnet 4 요청이 1M 문맥 창용 서버로 잘못 라우팅 ② TPU 서버 설정 오류로 드물어야 할 토큰(태국어·중국어 문자 등)이 섞임 ③ approximate top-k 연산 컴파일러 결함으로 토큰 선택 오류. 기존 평가로 잡히지 않음 |
| **R2** | Anthropic, 2026년 3~4월 (Claude Code) | ① 기본 추론 강도 high→medium(지연 절감 목적, 4/7 원복) ② 캐싱 최적화 결함으로 이전 추론이 매 턴 삭제되어 모델이 잊어버리는 것처럼 보임(4/10 수정) ③ 장황함을 줄이는 시스템 프롬프트 변경이 다른 변경과 결합해 코딩 품질 저하, 한 평가에서 3% 하락(4/20 원복) |
| **R3** | OpenAI, 2025년 4월 | GPT-4o 업데이트(4/24~25)가 아첨 경향을 띠어 4/28 롤백 시작. 오프라인 평가가 아첨을 잡을 만큼 넓지 않았고, A/B 테스트에 신호가 없었음 |

출처: [Anthropic 2025-09-17](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues) / [Anthropic 2026-04-23](https://www.anthropic.com/engineering/april-23-postmortem) / [OpenAI 2025](https://openai.com/index/expanding-on-sycophancy/)

---

## 3. 공통 규약

### 3.1 시나리오 ID 규칙

| 항목 | 규칙 |
| --- | --- |
| 형식 | `SCN-{3자리 숫자}` (예: `SCN-001`) |
| 파일명 | `SCN-{3자리}-{kebab-case-제목}.yaml` (예: `SCN-001-prompt-change.yaml`) |
| 위치 | `injection/scenarios/` |
| API | `POST /api/v1/injections`의 `scenarioId`에 `SCN-001` 형식 그대로 전달 |
| DB | `injection_runs.scenario_id`에 동일 문자열 저장 |
| 정상 대조 | `SCN-000` 예약 |
| 채번 | 순차 부여. 폐기 시 결번 유지 (재사용 금지) |

### 3.2 정답 라벨 정의

**라벨 대상이 두 개다.**

| 라벨 대상 | 값 | 쓰이는 지표 |
| --- | --- | --- |
| **회차(run)** | 1=주입 있음 / 0=정상 | 탐지율(1에서), 오탐 횟수(0에서) |
| **변경(change)** | 원인(정답, `is_decoy=false`) / 디코이(오답, `is_decoy=true`) | Top-1·Top-3 정확도 |
- 회차가 `1`이어도 그 안의 모든 변경이 정답은 아니다. 디코이 변경은 같은 회차 안에서 오답이다.
- 회차가 `ABORTED`면 라벨과 무관하게 **모든 지표에서 제외**한다(policies.md 9.2).

**저하 확인 절차**: 주입했다고 품질이 반드시 떨어지는 것은 아니다. 시나리오마다 주입 전·후 응답을 2단계 전수 채점해 통계적으로 달라졌는지 먼저 확인한다. 저하가 확인되지 않은 시나리오는 과제 C 탐지율 분모에서 제외하고 "저하 없음"으로 따로 보고한다.

### 3.3 탐지 난이도 등급

| 등급 | 설명 | 판정 기준 |
| --- | --- | --- |
| `EASY` | **고정 임계값만으로도** 탐지된다 | 평균 품질 점수 하락 폭이 크고 즉시 발현 |
| `MEDIUM` | 평균은 크게 안 변하지만 **분포가 변해** 통계 검정이나 임베딩 거리가 필요하다 | 일부 질문군에서만 저하, 분산 증가 |
| `HARD` | 하락 폭이 작거나 **지연 발현**이라 5분 창으로는 잡기 어렵다 | 창을 넓혀야 보이거나 저하가 누적되어 나타남 |

난이도는 **설계 시 예상값**이며 SP3 실험 후 실측 탐지율로 재분류한다. 예상과 실측이 다르면 그 차이 자체가 보고할 결과다.

### 3.4 유형 분류

**(A) 변경 유형 — 주 분류 (무엇을 바꿨는가)**

| 유형 코드 | 설명 | 대응 사고 유형 |
| --- | --- | --- |
| `PROMPT_CHANGE` | 시스템·사용자 프롬프트 템플릿 변경 | R2-③ |
| `MODEL_SWAP` | 생성 모델을 다른 모델로 교체 | R3 |
| `RETRIEVAL_NARROW` | 검색 문서 수(top-k) 축소 | R2-① (기본값 하향) |
| `CHUNK_CHANGE` | 청크 크기 변경 | R1-① (문맥 조건 변화) |
| `INDEX_CORRUPTION` | 검색 인덱스 일부 손상(근거 문서 누락) | R1, R2-② |
| `DECOY_NEUTRAL` | 품질에 영향 없는 변경(디코이) | — |
| `CONTROL` | 변경 없음(정상 대조) | — |

**(B) 발현 유형 — 보조 분류 (응답에 어떻게 나타나는가)**

| 유형 코드 | 설명 |
| --- | --- |
| `FACTUAL_ERROR` | 사실과 다른 정보 생성 |
| `HALLUCINATION` | 존재하지 않는 정보 생성 |
| `PARTIAL_TRUTH` | 일부만 맞고 일부는 틀림 |
| `OMISSION` | 근거에 있는 정보를 빠뜨림 |
| `STYLE_SHIFT` | 내용은 유지하되 길이·어조가 변함 |

`STYLE_SHIFT`는 1단계 환각 탐지 모델이 잡지 못하는 것이 정상이다. 임베딩 거리 판정기가 유리할 것으로 예상하며, 이 대비가 과제 C의 핵심 비교 축이다.

---

## 4. YAML 스키마

### 4.1 스키마 정의 — 회차 단위 주입

```yaml
scenario_id: string          # SCN-{3자리}. 필수. API scenarioId와 동일 문자열
title: string                # 시나리오 제목
change_type: string          # 3.4(A) 변경 유형 코드
expression_type: string      # 3.4(B) 발현 유형 코드(예상값)
difficulty: string           # EASY | MEDIUM | HARD
label: integer               # 0 또는 1. 회차 라벨
injected: boolean            # label=1이면 true

baseline:                    # 회차 시작 시 적용할 기준 설정
  prompt: string             # configs/prompts/ 버전명
  model: string              # 생성 모델 식별자
  top_k: integer
  chunk_size: integer

traffic:                     # 트래픽 생성기 설정
  question_set: string       # 질문 집합 식별자 (msmarco_eval_v1 기준)
  rps: float                 # 초당 요청 수
  duration_min: integer      # 회차 총 길이(분)

seed: integer                # 난수 시드. 재현성 확보. 필수

events:                      # 주입 이벤트 목록. label=0이면 디코이만 또는 빈 배열
  - at_minute: integer       # 회차 시작 기준 주입 시점(분). 상대 시각
    change:                  # 교체할 설정. baseline의 부분 집합
      {key}: {value}
    is_decoy: boolean        # true면 정답이 아님
    note: string             # 이 이벤트의 의도

expected:                    # 설계 시 예상. 실측과 비교해 보고한다
  detectable_by: [string]    # 탐지 가능할 것으로 보는 판정기 목록
  expected_delay_min: integer
  quality_drop: string       # LARGE | MODERATE | SMALL | NONE

metadata:
  source: string             # 시나리오 근거
  created_by: string
  created_at: string         # ISO 8601 UTC
```

### 4.2 스키마 검증 규칙

실행 전 서버가 검증하고, 위반 시 `422 SCENARIO_NOT_FOUND` 또는 `400 INVALID_REQUEST`로 거부한다.

| 규칙 | 위반 시 |
| --- | --- |
| `scenario_id`가 파일명과 일치 | 거부 |
| `label: 1`이면 `is_decoy: false` 이벤트가 1개 이상 | 거부 |
| `label: 0`이면 `is_decoy: false` 이벤트가 0개 | 거부 |
| `events[].at_minute < traffic.duration_min` | 거부 |
| `events[].change`의 키가 `baseline`에 존재 | 거부 |
| `change`가 가리키는 버전이 `configs/`에 존재 | 거부 |
| `at_minute`이 같은 이벤트가 둘 이상 없음 | 거부 |
| 주입 전 정상 구간이 최소 15분 | 경고 (표본 부족으로 드리프트 판정 보류 가능) |

### 4.3 레코드 단위 스키마 (보조, 과제 A 보조 평가셋용)

과제 A의 보조 평가셋이 필요해질 때 사용한다. **현재 SP2·SP3 계획에는 사용하지 않는다.**

```yaml
scenario_id: string
type: string           # 3.4(B) 발현 유형
difficulty: string
label: integer
input:
  context: string      # 근거 문맥
  query: string        # 사용자 질의
output:
  response: string     # 주입된 응답
  ground_truth: string
injection:             # label=1일 때만
  target_span: string  # 오류 구간 (인터페이스 HallucinationSpan과 동일 오프셋 규약)
  error_description: string
```

---

## 5. 디코이 규칙

### 5.1 디코이 정의

목적: **원인 지목의 난이도 확보.** 회차 안에 변경이 하나뿐이면 "가장 최근 변경을 고르는" 규칙 기반 방법이 항상 정답이 되어 에이전트의 기여를 측정할 수 없다.

이 프로젝트에서 디코이 = **품질에 영향을 주지 않는 변경**이다. 비율: 주입 회차마다 **디코이 1~2건**, 전체 변경 이벤트 중 약 50%. 배치: 정답 주입의 **5~15분 전**에 최소 1건.

### 5.2 디코이 생성 규칙

- **규칙 1**: 디코이는 품질에 실제로 영향을 주지 않아야 한다. 영향이 불확실한 변경은 쓰지 않는다.
- **규칙 2**: 디코이도 `version_changes`에 정상적으로 기록된다. 에이전트가 같은 후보 목록을 본다.
- **규칙 3**: `is_decoy: true`로 명시한다.
- **규칙 4**: 디코이는 정답 주입보다 시간상 앞에 둔다.
- **규칙 5**: 콘솔 설정 변경(`source='console'`)도 디코이가 될 수 있다.
- **규칙 6**: 디코이 종류를 회차마다 돌려 쓴다.

### 5.3 디코이 후보 목록

| 코드 | 변경 내용 | 품질 무영향 근거 |
| --- | --- | --- |
| `D-NOOP` | 주석·공백만 바꾼 파일 재배포 | 설정값은 같고 해시만 바뀜 |
| `D-LOGLEVEL` | 로그 레벨 변경 (`INFO` → `DEBUG`) | 응답 생성 경로에 영향 없음 |
| `D-ROUTING` | 라우팅 정책 τ 조정 (`0.5` → `0.55`) | 생성 품질에 영향 없음(검사 비용만 변함) |
| `D-NOTIFY` | 알림 쿨다운 변경 (`30분` → `45분`) | 알림 빈도만 변함 |
| `D-TIMEOUT` | LLM 호출 타임아웃 상향 (`30s` → `40s`) | 정상 구간에서 발동하지 않음 |

`D-NOOP` 주의: 내용 해시가 같으면 변경으로 기록되지 않으므로(policies.md 3.3), **의미 없는 주석을 추가해 해시만 바꾼 파일**을 별도 준비한다.

---

## 6. 시나리오 목록

| ID | 제목 | 변경 유형 | 발현 유형 | 난이도 | 라벨 | 모델 파트 | 서비스 파트 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SCN-000 | 정상 대조 회차 | `CONTROL` | — | — | 0 | ✅ | ✅ |
| SCN-001 | 프롬프트 간결화 변경 | `PROMPT_CHANGE` | `OMISSION` | MEDIUM | 1 | ✅ | ✅ |
| SCN-002 | 생성 모델 교체 | `MODEL_SWAP` | `FACTUAL_ERROR` | EASY | 1 | ✅ | ✅ |
| SCN-003 | 검색 문서 수 축소 | `RETRIEVAL_NARROW` | `OMISSION` | MEDIUM | 1 | ✅ | ✅ |
| SCN-004 | 청크 크기 변경 | `CHUNK_CHANGE` | `PARTIAL_TRUTH` | HARD | 1 | ✅ | ✅ |
| SCN-005 | 검색 인덱스 손상 | `INDEX_CORRUPTION` | `HALLUCINATION` | EASY | 1 | ✅ | ✅ |

SP2에서는 **SCN-001 하나만 수동 주입으로 시연**한다. SP3에서 6종 × 10회를 실행한다.

---

## 7. 시나리오 상세 신규 추가 템플릿

> 신규 시나리오를 추가할 때 아래 링크의 시나리오 템플릿을 복사해 새로 만들고, 8장에 링크를 붙여넣는다.  
> 모델 파트 → 서비스 파트 순으로 작성한다.  
> 추가 후 5장 시나리오 목록도 함께 갱신한다.

시나리오 템플릿: [docs\experiments\scenarios\SCN-000-template](docs\experiments\scenarios\SCN-000-template)

---

## 8. 시나리오 상세

> 링크로 관리.

[SCN-001: 프롬프트 간결화 변경](docs\experiments\scenarios\SCN-001-prompt-simplification.md)

[SCN-002: 생성 모델 교체](docs\experiments\scenarios\SCN-002-model-replacement.md)

[SCN-003: 검색 문서 수 축소](docs\experiments\scenarios\SCN-003-retrieval-doc-reduction.md)

[SCN-004: 청크 크기 변경](docs\experiments\scenarios\SCN-004-chunk-size-change.md)

[SCN-005: 검색 인덱스 손상](docs\experiments\scenarios\SCN-005-index-corruption.md)

---

## 9. 실행 절차

### 9.1 실행 전 점검

| 항목 | 확인 내용 |
| --- | --- |
| 설정 파일 | `change`가 가리키는 버전이 `configs/`에 커밋되어 있는가 |
| 단가표 | 교체 모델이 `configs/pricing.yaml`에 있는가 |
| 디코이 파일 | `D-NOOP`용 해시 변경 파일이 준비되어 있는가 |
| 질문 집합 | `question_set`이 적재되어 있는가 |
| 서버 상태 | 검사 큐(`app.eval.queue.depth`)가 비어 있는가 |
| 동시 실행 | `RUNNING` 상태 회차가 없는가 |

### 9.2 실행과 종료

1. `POST /api/v1/injections`로 실행한다.
2. `202` 응답의 `runId`로 진행 상황을 폴링한다(10초 간격).
3. 회차가 끝나면 모든 `injection_events.applied_at`이 채워졌는지 확인한다. 비어 있으면 `ABORTED`로 표시하고 데이터를 폐기한 뒤 재실행한다.
4. 검사 큐가 비워질 때까지 기다린 뒤 지표를 집계한다.

### 9.3 재현성 확인

| 확인 항목 | 방법 |
| --- | --- |
| 질문 순서 | 같은 시드로 2회 실행해 `traces` 질문 순서 비교 |
| 주입 시점 | `planned_at` 대비 `applied_at` 편차 수 초 이내 |
| 시나리오 무결성 | `injection_runs.scenario_hash`가 파일 해시와 일치 |
| 설정 반영 | 주입 직후 트레이스의 `app.*` 속성이 바뀐 값으로 기록되는지 |

### 9.4 반복 실행 계획

| 시나리오 | 시드 범위 | 회차 수 | 길이 | 예상 총 시간 |
| --- | --- | --- | --- | --- |
| SCN-000 | 1000~1009 | 10 | 90분 | 15시간 |
| SCN-001 | 42~51 | 10 | 90분 | 15시간 |
| SCN-002 | 43~52 | 10 | 90분 | 15시간 |
| SCN-003 | 44~53 | 10 | 90분 | 15시간 |
| SCN-004 | 45~54 | 10 | 120분 | 20시간 |
| SCN-005 | 46~55 | 10 | 90분 | 15시간 |
| **합계** | — | **60회** | — | **약 95시간** |

서버 가동 시간 예산(최대 168시간, SP3 1주 — 기획서 6.3)의 절반 이상을 차지한다. 남은 시간으로 개발·배포·시연 리허설까지 해야 하므로 서버만으로는 여유가 없다. 반복 실험은 로컬 Compose에서 수행하고 서버에서는 시연용 회차만 돌리는 방안을 IS-9에서 결정한다. 예산이 부족하면 SCN-004(가장 긴 HARD 시나리오)부터 5회로 줄이는 것을 1순위로 한다.

---

## 10. 평가 지표 연결

| 지표 | 산출 방법 | 사용 시나리오 |
| --- | --- | --- |
| 탐지율 | 주입 회차 중 인시던트가 생성된 비율 | SCN-001~005 |
| 탐지 지연 | `incidents.detected_at` − `injection_events.applied_at`(정답) | SCN-001~005 |
| 오탐 횟수 | 정상 구간의 `is_drift=true` 창 수 + `DISMISSED` 인시던트 | **SCN-000** + 각 회차 주입 전 구간 |
| 판정기 비교 | 같은 창에 대한 3종 판정기의 결과 차이 | 전체 |
| 시간 창 비교 | 5분 vs 15분 창의 탐지율·오탐 차이 | 전체 (특히 SCN-004) |
| Top-1 정확도 | `incidents.top1_version_change_id` = 정답 `version_change_id` | SCN-001~005 |
| Top-3 정확도 | `agent_result`의 상위 3개 안에 정답 포함 | SCN-001~005 |
| 기준선 대비 | 규칙 기반(직전 변경 지목)의 정확도와 비교 | SCN-001~005 (디코이가 있어야 의미) |
| 조사 비용 | `agent_steps`의 호출 수·토큰 합계 | SCN-001~005 |

**오탐 측정에 SCN-000이 필수다.** 주입 회차의 주입 전 구간만으로는 표본이 부족하다.

**디코이가 없으면 "기준선 대비" 항목이 무의미해진다.** 규칙 기반이 100%가 되어 에이전트가 이길 수 없는 비교가 된다.

---

## 미결정 사항

| # | 항목 | 담당 | 기한 |
| --- | --- | --- | --- |
| IS-1 | **[모델 파트] 전체 확정** — 사고 대응 근거·탐지 포인트·정답 라벨·기대 신호. 현재 초안 상태 | `AI-MDL` | SP3 시작 전 |
| IS-2 | 난이도 등급 실측 재분류 — 설계 예상값과 SP3 실측 탐지율 비교 후 갱신 | `AI-MDL` | SP3 |
| IS-3 | SCN-003 `top_k` 주입값 확정 — 현재 5→2. 대안 5→1(더 극단적, 더 탐지 쉬움)과 비교 검토 필요 | `BOTH` | SP3 시작 전 |
| IS-4 | SCN-004 `chunk_size` 주입 방향 확정 — 현재 512→1024(크게). 대안 512→128(작게)은 다른 발현 패턴 발생 | `BOTH` | SP3 시작 전 |
| IS-5 | SCN-004 재인덱싱 소요 시간 측정 — 회차 길이 120분 적정성 확인 | `AI-SVC` | SP3 시작 전 |
| IS-6 | SCN-005 `index_drop_ratio` → `version_changes` 기록 방식 — 안 A: `kind=retrieval`로 기록 / 안 B: 기록하지 않고 "변경 이력에 없는 원인" 시나리오로 둠(에이전트 평가 기준 별도 정의 필요) | `AI-SVC` + `AI-MDL` | SP3 시작 전 |
| IS-7 | SCN-002 교체 모델 확정 — 채점 모델과 겹치지 않는 이전 세대 소형 모델 | `AI-SVC` | SP3 |
| IS-8 | `qa-v1.3-terse` 프롬프트 간결화 강도 확정 — 너무 강하면 EASY가 되어 MEDIUM 사례 의미 감소 | `BOTH` | SP2 11주차 |
| IS-9 | 60회 실행의 실행 환경(로컬/서버)·가동 시간·LLM 비용 재산정 — 예산 초과 시 SCN-004부터 회차 축소 | `BOTH` | SP3 시작 전 |
| IS-10 | `app.retrieval.doc_count < top_k` 불일치의 자동 경보 도입 여부 | `AI-SVC` | SP3 / 범위 외 가능성 있음 |

---

end.