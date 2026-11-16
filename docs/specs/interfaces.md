# 인터페이스 계약

> **최종 수정**: 2026-10-31
> 

---

## 1. 개요

- **목적**: `AI-SVC`(서비스·인프라)와 `AI-MDL`(모델·평가) 두 파트가 **서로를 기다리지 않고 병렬 개발**할 수 있도록, 두 파트가 맞닿는 지점의 입출력 계약을 고정한다. 동시에 공개 모델 ↔ 자체 모델, 판정기 3종, LLM 제공자, 알림 채널처럼 **교체가 예정된 구성요소**의 경계를 정의한다(ADR-024).
- **범위**: 이 문서는 **Python Protocol 기반 인터페이스만** 다룬다.
    - HTTP API 계약(Console API, Ingest API) → `docs/specs/api.md`
    - DB 스키마 → `docs/erd.md`
    - 기능 요구사항 명세 → `docs/specs/SDD.md`
    - 운영 규칙·TTL·재시도 정책 → `docs/policies.md`
    - MCP 도구의 JSON 스키마 → `docs/specs/api.md` (에이전트 도구 절)
- **구현 언어**: Python 3.12 (`typing.Protocol`, `TypedDict`, `dataclass`)
- **위치**: `src/interfaces/` — `CODEOWNERS` 승인 필수 경로다. 이 디렉터리를 바꾸는 PR은 상대 파트의 승인을 받아야 한다(ADR-009).
- **확정 기한**: `Detector` · `DriftDetector` · Console API 응답 형식은 **2026-10-28(SP2 시작 주)까지** 합의한다(요구사항 T3-01).

### 1.1 설계 방침

| 방침 | 내용 | 근거 |
| --- | --- | --- |
| 동기 우선 | 모든 인터페이스는 동기 메서드로 정의한다. 비동기 처리는 워커가 담당하므로 계약이 async일 필요가 없다 | ADR-006 |
| 배치 우선 | 추론 비용이 드는 인터페이스는 **단건이 아니라 리스트를 받는다**. CPU 배치 추론이 전제이기 때문 | ADR-023 |
| 순수 함수 지향 | 인터페이스 구현체는 DB·네트워크 상태를 직접 건드리지 않는다. I/O는 호출자(워커)가 수행한다 | 테스트 용이성 |
| 상태 비보존 | 구현체는 호출 간 상태를 유지하지 않는다. 모델 적재 같은 초기화는 생성자에서 끝낸다 | 워커 재기동 안전성 |
| 교체 가능성 | 구현체 선택은 설정 파일(`configs/`)로만 한다. 코드에서 분기하지 않는다 | ADR-005, ADR-024 |

---

## 2. 공통 타입 정의

여러 인터페이스가 공유하는 타입이다. `src/interfaces/types.py`에 둔다.

### 2.1 공유 데이터 타입

```python
from typing import TypedDict, NotRequired, Sequence

class RetrievedDoc(TypedDict):
    """RAG 검색으로 가져온 근거 문서 1건. traces.contexts의 원소와 동일 구조."""
    doc_id: str            # 코퍼스 내 문서 식별자
    text: str              # 문서(청크) 본문
    score: float           # 검색 유사도. 범위 제한 없음(검색기마다 척도가 다름)

class EvalInput(TypedDict):
    """검사 대상 1건. 1·2단계가 같은 입력 구조를 쓴다."""
    trace_id: str                    # OTel trace id (hex 32자리)
    question: str                    # 사용자 질문
    answer: str                      # 생성된 응답. 빈 문자열 금지
    contexts: Sequence[RetrievedDoc] # 근거 문서. 비어 있을 수 있음(검색 실패)

class HallucinationSpan(TypedDict):
    """응답 안에서 근거로 뒷받침되지 않는 구간. erd.md evaluations.hallucination_spans의 원소."""
    start: int                       # 응답 문자열 기준 시작 오프셋 (0-based, 포함)
    end: int                         # 끝 오프셋 (exclusive)
    text: str                        # 해당 구간 원문. answer[start:end]와 반드시 일치

class DetectionResult(TypedDict):
    """1단계 탐지 결과."""
    trace_id: str
    score: float                           # 환각 의심 점수. 0.0~1.0, 높을수록 의심↑
                                           # stage 1 전용. erd.md 1장 점수 방향 원칙 참조.
                                           # 라우팅 규칙 score >= τ 와 방향이 일치해야 한다.
    spans: Sequence[HallucinationSpan]     # 의심 구간. 없으면 빈 리스트
    latency_ms: int                        # 추론 소요 시간(배치 분할 시 건당 환산)

class JudgeResult(TypedDict):
    """2단계 LLM 채점 결과."""
    trace_id: str
    score: float                     # 품질 점수. 0.0~1.0, 높을수록 품질 좋음↑
                                     # stage 2 전용. stage 1 score와 방향이 반대임에 주의.
                                     # erd.md 1장 점수 방향 원칙 참조.
    label: str                       # EvalLabel 값
    reason: str                      # 판정 이유(사람이 읽는 텍스트). erd.md evaluations.reason_text
    usage: "TokenUsage"
    cost_usd: float                  # 채점 1건 비용. 0 이상. erd.md evaluations.cost_usd
    latency_ms: int                  # erd.md evaluations.latency_ms

class RoutingDecision(TypedDict):
    """2단 라우팅 판정 결과."""
    trace_id: str
    to_stage2: bool                  # 2단계로 보낼지
    reason: str                      # RoutedReason 값. erd.md evaluations.routed_reason

class WindowStats(TypedDict):
    """시간 창 1개의 집계 결과. DriftDetector 입력이자 quality_windows의 원천.

    Note: 창 배분 기준은 traces.started_at이다. evaluations.created_at이나
    embeddings.created_at을 기준으로 창을 나누지 않는다. 비동기 처리 지연이
    창 귀속에 영향을 주지 않게 하기 위함이다(erd.md 1장 창 집계 기준 원칙, ADR-029).
    """
    window_start: str                # ISO 8601 UTC. traces.started_at 기준 창 시작
    window_end: str                  # ISO 8601 UTC
    sample_count: int                # 창 내 표본 수(traces 기준)
    scores: Sequence[float]          # 창 내 품질 점수 목록.
                                     # 콘솔 표시용이므로 변환 후 값(stage2 또는 1-stage1_score)
    hallucination_rate: float        # 환각 판정 비율. 0.0~1.0
    embeddings: NotRequired[Sequence[Sequence[float]]]  # 응답 임베딩(임베딩 거리 판정기용).
                                                        # 256 word piece 초과 응답은 잘림에 주의(ADR-029 미결 D-6)

class DriftVerdict(TypedDict):
    """드리프트 판정 결과. erd.md quality_windows 테이블에 저장된다."""
    is_drift: bool                   # 저하로 판정했는지
    drift_score: float | None        # 판정 통계량. 보류 시 None
    deferred: bool                   # 표본 부족 등으로 판정을 보류했는지. True이면 is_drift는 반드시 False
    detail: str                      # 판정 근거 요약(로그·화면 표시용). erd.md quality_windows.detector_config

class TokenUsage(TypedDict):
    input_tokens: int                # 0 이상
    output_tokens: int               # 0 이상

class LLMMessage(TypedDict):
    role: str                        # "system" | "user" | "assistant"
    content: str

class LLMResponse(TypedDict):
    text: str                        # 생성된 본문
    model: str                       # 실제 응답한 모델 식별자
    usage: TokenUsage
    latency_ms: int

class NotificationPayload(TypedDict):
    """알림 1건. 채널 구현체가 각자의 형식으로 변환한다. erd.md notifications.payload"""
    title: str                       # 한 줄 제목
    summary: str                     # 하락 시점·지표 요약
    cause_candidate: NotRequired[str]  # 원인 후보 1순위 설명
    evidence: NotRequired[str]         # 근거 요약
    console_url: str                 # 인시던트 상세 링크
    dedup_key: str                   # 쿨다운 판정 키. erd.md notifications.dedup_key
```

### 2.2 공통 Enum

```python
from enum import Enum

class RoutedReason(str, Enum):
    """erd.md evaluations.routed_reason과 동일 값."""
    THRESHOLD = "threshold"   # 1단계 점수가 임계값 τ 이상이라 2단계로 보냄
    SAMPLE = "sample"         # 무작위 표본(비율 r)으로 2단계로 보냄
    NONE = "none"             # 2단계로 보내지 않음

class EvalLabel(str, Enum):
    """erd.md evaluations.label과 동일 값."""
    SUPPORTED = "SUPPORTED"           # 근거 문서로 뒷받침됨
    HALLUCINATED = "HALLUCINATED"     # 근거 없는 내용이 포함됨
    UNVERIFIABLE = "UNVERIFIABLE"     # 근거 문서로는 판단 불가

class DriftMetric(str, Enum):
    """erd.md quality_windows.metric과 동일 값."""
    QUALITY_SCORE = "quality_score"
    HALLUCINATION_RATE = "hallucination_rate"
    EMBEDDING_DISTANCE = "embedding_distance"

class DriftDetectorName(str, Enum):
    """DriftDetector 전용 식별자. erd.md quality_windows.detector_name과 동일 값.
    Detector(1단계 탐지 모델)의 evaluator_key와는 별개다.
    """
    FIXED_THRESHOLD = "fixed_threshold"       # 고정 임계값
    KS_TEST = "ks_test"                       # 분포 비교(통계 검정)
    EMBEDDING_DISTANCE = "embedding_distance" # 임베딩 거리

class NotificationChannel(str, Enum):
    """erd.md notifications.channel과 동일 값."""
    SLACK = "slack"
    EMAIL = "email"
```

> **주의:** `DriftDetectorName`은 `DriftDetector`(드리프트 판정기) 전용 식별자다. `Detector`(1단계 환각 탐지 모델)의 `name`은 자유 형식 문자열(`{모델명}-{서빙형식}`)이며 이 Enum과 무관하다.
> 

---

## 3. 인터페이스 목록

| 인터페이스명 | 설명 | 초안 | 확정 | 상태 |
| --- | --- | --- | --- | --- |
| `Detector` | 1단계 경량 환각 탐지 | `AI-SVC` | `AI-MDL` | 확정 |
| `Judge` | 2단계 LLM 정밀 채점 | `AI-SVC` | `AI-MDL` | 설계 |
| `Router` | 2단 검사 라우팅 판정 (τ·r) | `AI-SVC` | `AI-MDL` | 설계 |
| `DriftDetector` | 시간 창 기반 드리프트 판정 | `AI-MDL` | `AI-SVC` | 확정 |
| `Embedder` | 응답 임베딩 생성 | `AI-SVC` | `AI-MDL` | 설계 |
| `LLMClient` | 제공자 독립 LLM 호출 | `AI-SVC` | `AI-SVC` | 설계 |
| `CostCalculator` | 단가표 기반 요청 단위 비용 계산 | `AI-SVC` | `AI-SVC` | 설계 |
| `Notifier` | 인시던트 알림 발송 | `AI-SVC` | `AI-SVC` | 설계 |
- **초안**은 인터페이스 시그니처를 먼저 제안하는 쪽, **확정**은 구현 가능 여부를 검토해 최종 승인하는 쪽이다.
- `Detector`·`DriftDetector`는 **2026-10-28까지 확정**한다(T3-01).
- 상태가 `확정`으로 바뀐 뒤에는 변경 이력(이 문서 마지막 절)에 기록하고 버전을 올린다.

---

## 4. 인터페이스 상세 신규 추가 템플릿

> 신규 인터페이스를 추가할 때 아래 블록을 복사해 5장에 붙여넣는다.   
> 추가 후 3장 인터페이스 목록, 6장 예외 코드도 함께 갱신한다.

인터페이스 템플릿: [docs\specs\template\interfaces-template.md](docs\specs\template\interfaces-template.md)

---

## 5. 인터페이스 상세

### 5.1 Detector

| 항목 | 값 |
| --- | --- |
| **목적** | 모든 응답을 CPU에서 검사해 환각 의심 점수와 근거 없는 구간을 돌려준다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-MDL` |
| **상태** | 확정 |
| **구현체** | `LettuceDetectDetector`(기준선·임시) / `OnnxTokenClassifierDetector`(자체 학습 모델) |
| **소비자** | `src/eval/worker.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `detect_batch` | 여러 건을 한 번에 검사한다 | sync |
| `name` | 평가자 식별자를 반환한다(속성) | sync |

#### `detect_batch`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `inputs` | `Sequence[EvalInput]` | Y | 검사 대상 목록 | 1~16건. 빈 리스트 금지 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[DetectionResult]` | 입력과 **같은 길이·같은 순서**의 결과 목록 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `DetectorLoadError` | 모델 가중치·ONNX 파일 적재 실패 |
| `DetectorInputError` | 빈 리스트, `answer`가 빈 문자열, 배치 크기 초과 |
| `DetectorInferenceError` | 추론 중 런타임 오류 |

**코드 예시**

```python
from typing import Protocol, Sequence

class Detector(Protocol):
    @property
    def name(self) -> str:
        """평가자 식별자. erd.md evaluations.evaluator_key에 그대로 저장된다.
        형식: "{모델명}-{서빙형식}", 100자 이내.
        예: "lettucedetect-modernbert-base-onnx-int8"
            "team17-deberta-small-onnx-int8"
            "lettucedetect-modernbert-large-fp32"  (기준선, 최적화 전)

        모델명과 서빙 형식(fp32/onnx-int8 등)을 모두 포함해야
        최적화 전후를 같은 트레이스에서 비교할 수 있다(ADR-027).
        DriftDetectorName Enum과는 별개의 자유 형식 문자열이다.
        """
        ...

    def detect_batch(self, inputs: Sequence[EvalInput]) -> list[DetectionResult]:
        """근거 문서로 뒷받침되지 않는 구간을 찾는다.

        score 방향: 0.0(clean) → 1.0(likely hallucinated). 높을수록 의심.
        라우팅 규칙 score >= τ 와 방향이 일치해야 한다(erd.md 1장 점수 방향 원칙).

        Args:
            inputs: 검사 대상 1~64건. 각 항목의 answer는 빈 문자열이 아니어야 한다.

        Returns:
            입력과 같은 길이·순서의 결과 목록. 의심 구간이 없으면 spans는 빈 리스트.

        Raises:
            DetectorInputError: 입력이 비었거나 배치 크기를 초과한 경우
            DetectorInferenceError: 추론 실패
        """
        ...
```

**구현 노트**

- **순서 보장이 계약의 핵심이다.** 내부에서 정렬·재배치를 하더라도 반환 시 입력 순서로 되돌려야 한다.
- `contexts`가 빈 리스트인 경우(검색 실패)에도 예외를 던지지 않는다. 이 상황이 "검색 인덱스 손상" 주입 시나리오의 탐지 대상이다.
- 최대 입력 길이를 넘는 경우 내부에서 문맥을 분할 처리한다. 예외를 던지지 않는다.
- 모델 적재는 **생성자에서 끝낸다.** `detect_batch` 호출 시점에 지연 로딩하면 첫 배치의 지연 측정이 왜곡된다.
- `name`은 `{모델명}-{서빙형식}` 형식으로 모델·양자화 여부가 식별 가능해야 한다. 최적화 전후 비교 실험에서 같은 트레이스에 대해 두 평가자가 각각 행을 만든다.

### 5.2 Judge

| 항목 | 값 |
| --- | --- |
| **목적** | 의심 응답과 무작위 표본을 LLM으로 정밀 채점하고 판정 이유를 남긴다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-MDL` |
| **상태** | 설계 |
| **구현체** | `ClaudeJudge`(기본) / `CrossProviderJudge`(교차 검증용) |
| **소비자** | `src/eval/worker.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `judge_batch` | 여러 건을 채점한다 | sync |
| `name` | 채점자 식별자를 반환한다(속성) | sync |

#### `judge_batch`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `inputs` | `Sequence[EvalInput]` | Y | 채점 대상 | 1~50건 |
| `use_batch_api` | `bool` | N | Batch API 사용 여부 | 기본 `False`. `True`면 최대 24시간 대기 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[JudgeResult]` | 입력과 같은 길이·순서 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `LLMRateLimitError` | 429 응답 — 재시도 대상 |
| `LLMTransientError` | 5xx·타임아웃 — 재시도 대상 |
| `LLMPermanentError` | 4xx(400/401/403) — 재시도 금지 |
| `BudgetExceededError` | 지출 한도 도달 |
| `JudgeParseError` | 채점 결과를 정해진 구조로 파싱하지 못함 |

**코드 예시**

```python
class Judge(Protocol):
    @property
    def name(self) -> str:
        """채점자 식별자. erd.md evaluations.evaluator_key에 저장된다.
        채점 모델과 채점 프롬프트 버전을 함께 담는다.
        예: "claude-sonnet-mid-judge-v2"

        채점자 자체의 변동과 서비스 품질 저하를 구분하는 근거가 되므로
        프롬프트 버전을 포함해야 한다(기획서 11장 리스크).
        """
        ...

    def judge_batch(
        self,
        inputs: Sequence[EvalInput],
        use_batch_api: bool = False,
    ) -> list[JudgeResult]:
        """근거 일치 여부와 정확성을 채점하고 이유를 남긴다.

        score 방향: 0.0(bad) → 1.0(good). 높을수록 품질 좋음.
        stage 1 score(높을수록 의심)와 방향이 반대임에 주의(erd.md 1장 점수 방향 원칙).

        Raises:
            LLMRateLimitError / LLMTransientError: 재시도 가능
            LLMPermanentError / BudgetExceededError: 재시도 금지
            JudgeParseError: 1회 재시도 후에도 구조화 실패
        """
        ...
```

**구현 노트**

- 채점 결과는 **구조화된 형식으로 받아 파싱**한다. 파싱 실패는 1회 재시도 후 `JudgeParseError`로 올린다.
- `name`에 **채점 프롬프트 버전을 포함**한다.
- 생성 모델과 채점 모델은 등급이 분리되어야 한다(ADR-015). 구현체가 생성 모델과 같은 모델을 쓰지 않도록 기동 시 설정 검증에서 확인한다.
- `cost_usd`는 `CostCalculator`를 거쳐 채운다. 구현체가 자체 단가를 들고 있으면 안 된다.
- Batch API 사용 시에도 **반환 시점에는 결과가 완성되어 있어야 한다.** 대기는 구현체 내부에서 폴링으로 처리한다.

### 5.3 Router

| 항목 | 값 |
| --- | --- |
| **목적** | 1단계 점수와 정책(τ·r)에 따라 2단계 채점 대상을 고른다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-MDL` |
| **상태** | 설계 |
| **구현체** | `ThresholdSampleRouter` |
| **소비자** | `src/eval/worker.py`, 라우팅 정책 실험 스크립트 |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `route` | 1단계 결과 목록에 대해 2단계 전달 여부를 판정한다 | sync |

#### `route`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `results` | `Sequence[DetectionResult]` | Y | 1단계 결과 | 빈 리스트 허용(빈 결과 반환) |
| `threshold` | `float` | Y | 임계값 τ | 0.0~1.0 |
| `sample_rate` | `float` | Y | 무작위 표본 비율 r | 0.0~1.0 |
| `rng_seed` | `int | None` | N | 재현성용 시드 | 실험에서는 필수 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[RoutingDecision]` | 입력과 같은 길이·순서 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `RoutingConfigError` | τ 또는 r이 0.0~1.0 범위를 벗어남 |

**코드 예시**

```python
class Router(Protocol):
    def route(
        self,
        results: Sequence[DetectionResult],
        threshold: float,
        sample_rate: float,
        rng_seed: int | None = None,
    ) -> list[RoutingDecision]:
        """2단계 전달 대상과 사유를 판정한다.

        판정 규칙:
            score >= threshold          -> to_stage2=True,  reason="threshold"
            그 외 중 비율 sample_rate   -> to_stage2=True,  reason="sample"
            나머지                      -> to_stage2=False, reason="none"

        임계값 판정이 표본 추첨보다 먼저다. 임계값으로 선택된 건은
        표본 추첨 모집단에서 제외한다(불변식 참조).
        """
        ...
```

**구현 노트**

- **임계값 판정이 표본 추첨보다 먼저다.** 임계값으로 이미 선택된 건은 표본 추첨 모집단에서 제외한다. 그러지 않으면 `sample` 사유 건수가 부풀려져 누락률 계산이 왜곡된다.
- 표본 추출은 주입된 시드로만 난수를 쓴다. 전역 `random`을 쓰면 실험 재현성이 깨진다(policies.md 9.3).
- `sample_rate=0.0`은 문법적으로 허용하되, 실험 구간에서는 설정 검증이 경고를 낸다. 표본이 없으면 누락률을 계산할 수 없다(policies.md 3.2).
- 이 인터페이스는 **TDD 적용 대상**이다. 경계값(τ=0.0/1.0, r=0.0/1.0)과 분포 수렴 테스트를 먼저 작성한다(test-plan.md 8.1-1).

### 5.4 DriftDetector

| 항목 | 값 |
| --- | --- |
| **목적** | 시간 창 집계 결과를 보고 품질 저하가 발생했는지 판정한다 |
| **초안** | `AI-MDL` |
| **확정** | `AI-SVC` |
| **상태** | 확정 |
| **구현체** | `FixedThresholdDetector` / `KsTestDetector` / `EmbeddingDistanceDetector` |
| **소비자** | `src/drift/monitor.py` (APScheduler 기반 스케줄러) |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `judge` | 기준 구간과 현재 창을 비교해 판정한다 | sync |
| `name` | 판정기 식별자를 반환한다(속성) | sync |
| `required_metric` | 이 판정기가 사용하는 지표를 반환한다(속성) | sync |

#### `judge`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `current` | `WindowStats` | Y | 판정 대상 창 | — |
| `baseline` | `Sequence[WindowStats]` | Y | 기준 구간 창 목록 | 비어 있으면 판정 보류 |
| `config` | `dict[str, float]` | N | 민감도 등 판정기별 설정 | 구현체가 해석 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `DriftVerdict` | 판정 결과. 표본 부족 시 `deferred=True`로 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `DriftConfigError` | 필수 설정 누락 또는 범위 위반 |
| `DriftInputError` | `required_metric`에 필요한 필드가 `current`에 없음(예: 임베딩 누락) |

**코드 예시**

```python
class DriftDetector(Protocol):
    @property
    def name(self) -> str:
        """판정기 식별자. erd.md quality_windows.detector_name에 저장된다.
        DriftDetectorName Enum 값과 반드시 일치해야 한다.
        Detector(1단계 탐지 모델)의 evaluator_key와는 별개의 Enum이다.
        """
        ...

    @property
    def required_metric(self) -> str:
        """이 판정기가 사용하는 지표. DriftMetric Enum 값.
        호출자(Drift Monitor)는 이 값을 보고 WindowStats의 어떤 필드가 필요한지 판단한다.
        """
        ...

    def judge(
        self,
        current: WindowStats,
        baseline: Sequence[WindowStats],
        config: dict[str, float] | None = None,
    ) -> DriftVerdict:
        """현재 창이 기준 구간 대비 저하되었는지 판정한다.

        창 배분 기준은 traces.started_at이다(WindowStats 주석 참조).
        표본이 부족하면 예외를 던지지 않고 deferred=True로 반환한다.
        """
        ...
```

**구현 노트**

- **표본 부족은 예외가 아니다.** `sample_count < 30`이면 `deferred=True`, `is_drift=False`, `drift_score=None`으로 반환한다.
- `deferred=True`일 때 `is_drift`는 항상 `False`다(7.4 불변식).
- 판정기는 **DB를 조회하지 않는다.** `baseline` 구성은 호출자(Drift Monitor)의 책임이다.
- 세 판정기는 **같은 창에 대해 모두 호출되어 각각 기록**된다(policies.md 3.4).
- `config`의 키 이름 표준화는 미결 사항이다(이 문서 미결 사항 절 참조).
- 이 인터페이스는 `AI-MDL`이 초안을 내고 `AI-SVC`가 확정한다. 스케줄링·인시던트 생성은 `AI-SVC`의 책임이다(ADR-029).

### 5.5 Embedder

| 항목 | 값 |
| --- | --- |
| **목적** | 응답 텍스트를 고정 차원 벡터로 변환해 임베딩 분포 드리프트 감지에 쓴다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-MDL` |
| **상태** | 설계 |
| **구현체** | `SentenceTransformerEmbedder` (all-MiniLM-L6-v2, 384차원) |
| **소비자** | `src/eval/worker.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `embed_batch` | 텍스트 목록을 벡터로 변환한다 | sync |
| `dimension` | 출력 차원 수를 반환한다(속성) | sync |
| `name` | 임베딩 모델 식별자를 반환한다(속성) | sync |

#### `embed_batch`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `texts` | `Sequence[str]` | Y | 임베딩 대상 | 1~64건, 각 항목은 빈 문자열 금지 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[list[float]]` | 입력과 같은 길이·순서. 각 벡터의 길이는 `dimension`과 일치. 정규화(L2 norm=1) 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `EmbeddingError` | 모델 적재 실패 또는 추론 실패 |
| `DetectorInputError` | 빈 입력 |

**코드 예시**

```python
class Embedder(Protocol):
    @property
    def name(self) -> str:
        """erd.md embeddings.model_name에 저장된다.
        같은 model_name끼리만 거리 비교가 유효하다(erd.md embeddings 비고).
        """
        ...

    @property
    def dimension(self) -> int:
        """출력 차원. erd.md VECTOR(n)의 n과 일치해야 한다."""
        ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """텍스트를 정규화된 벡터로 변환한다(L2 norm=1).

        256 word piece를 초과하는 텍스트는 내부에서 잘린다.
        긴 응답의 경우 앞부분만 반영될 수 있음을 호출자가 인지해야 한다(ADR-029 미결 D-6).
        """
        ...
```

**구현 노트**

- `dimension`은 DB 스키마(`embeddings.vector VECTOR(384)`)에 직접 묶여 있다. 기동 시 설정 검증에서 `dimension`과 DB 차원이 일치하는지 확인한다.
- 벡터는 **정규화(L2 norm=1)해서 반환**한다. 코사인 거리 계산 시 호출자가 다시 정규화하지 않아도 된다.
- 임베딩 실패는 품질 점수 기반 판정까지 막지 않는다. 호출자는 `EmbeddingError`를 잡고 임베딩 없이 진행한다(policies.md 6.2).

### 5.6 LLMClient

| 항목 | 값 |
| --- | --- |
| **목적** | 제공자에 종속되지 않는 LLM 호출 경계. RAG 생성·채점·에이전트가 모두 이 인터페이스를 쓴다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-SVC` |
| **상태** | 설계 |
| **구현체** | `ClaudeClient`(기본) / `CrossProviderClient`(교차 검증용) |
| **소비자** | `src/rag/generator.py`, `src/eval/judge.py`, `src/agent/loop.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `complete` | 메시지 목록을 보내 응답을 받는다 | sync |
| `complete_with_tools` | 도구 목록을 함께 보내 도구 호출 또는 최종 응답을 받는다 | sync |

#### `complete`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `messages` | `Sequence[LLMMessage]` | Y | 대화 메시지 | 1건 이상 |
| `model` | `str` | Y | 모델 식별자 | 설정 파일에서 주입 |
| `max_tokens` | `int` | Y | 최대 출력 토큰 | 1 이상 |
| `temperature` | `float` | N | 샘플링 온도 | 0.0~1.0 |
| `timeout_sec` | `int` | N | 호출 타임아웃 | 기본값은 policies.md 2.1을 따른다 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `LLMResponse` | 본문·실제 모델명·토큰 사용량·지연 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `LLMRateLimitError` | 429 |
| `LLMTransientError` | 5xx, 타임아웃, 연결 오류 |
| `LLMPermanentError` | 400/401/403 |
| `BudgetExceededError` | 지출 한도 도달 |

**코드 예시**

```python
class LLMClient(Protocol):
    def complete(
        self,
        messages: Sequence[LLMMessage],
        model: str,
        max_tokens: int,
        temperature: float = 0.0,
        timeout_sec: int | None = None,
    ) -> LLMResponse:
        ...

    def complete_with_tools(
        self,
        messages: Sequence[LLMMessage],
        model: str,
        tools: Sequence[dict],
        max_tokens: int,
        timeout_sec: int | None = None,
    ) -> dict:
        """도구 호출 또는 최종 응답을 반환한다(에이전트 루프 전용).

        반환 구조:
            {"kind": "tool_use", "tool_name": str, "tool_args": dict, "usage": TokenUsage}
            {"kind": "final",    "text": str,       "usage": TokenUsage}
        """
        ...
```

**구현 노트**

- **재시도는 이 계층에서 하지 않는다.** 재시도 정책은 호출자가 policies.md 6.1에 따라 적용한다. 구현체는 예외를 재시도 가능/불가로 **분류해서 올리는 것**까지만 책임진다.
- 예외 분류는 상태 코드 기준으로만 한다. 응답 본문 문자열 매칭 금지(policies.md 6.1).
- `model`을 하드코딩하지 않는다. 생성은 소형, 채점·에이전트는 중형이며 값은 `configs/`에서 온다(ADR-015).
- `complete_with_tools`는 에이전트 루프 전용이다(ADR-007).
- 호출 1건마다 `usage`를 반드시 채운다. 비용 계산의 입력이기 때문이다.

### 5.7 CostCalculator

| 항목 | 값 |
| --- | --- |
| **목적** | 토큰 사용량과 단가표로 요청·검사 1건의 비용을 계산한다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-SVC` |
| **상태** | 설계 |
| **구현체** | `TableCostCalculator` (`configs/pricing.yaml` 기반) |
| **소비자** | 계측 SDK, `src/eval/judge.py`, `src/agent/loop.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `calculate` | 토큰 사용량을 USD 비용으로 환산한다 | sync |
| `pricing_version` | 적용 중인 단가표 버전을 반환한다(속성) | sync |

#### `calculate`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `model` | `str` | Y | 모델 식별자 | 단가표에 존재해야 함 |
| `usage` | `TokenUsage` | Y | 토큰 사용량 | 각 항목 0 이상 |
| `batch_api` | `bool` | N | Batch API 할인 적용 여부 | 기본 `False` |
| `cached_input_tokens` | `int` | N | 캐시 적중 입력 토큰 | 0 이상 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `float` | USD 비용. 0 이상. 소수점 6자리까지 유효(`NUMERIC(12,6)` 정합) |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `PricingNotFoundError` | 단가표에 해당 모델이 없음 |

**코드 예시**

```python
class CostCalculator(Protocol):
    @property
    def pricing_version(self) -> str:
        """적용 중인 단가표의 버전 이름. erd.md versions(kind='pricing')와 대응된다."""
        ...

    def calculate(
        self,
        model: str,
        usage: TokenUsage,
        batch_api: bool = False,
        cached_input_tokens: int = 0,
    ) -> float:
        ...
```

**구현 노트**

- 단가표에 없는 모델은 **0을 반환하지 않고 예외를 던진다.** 조용히 0으로 처리하면 비용 절감률이 과대 계상된다(ADR-025).
- 계산 결과는 소수점 6자리로 반올림해 `NUMERIC(12,6)` 컬럼과 정밀도를 맞춘다.
- 단가가 바뀌어도 **과거 기록을 소급 수정하지 않는다.** 새 단가표는 적용 시점 이후 요청에만 쓴다(policies.md 3.8).
- Batch API 할인(50%)과 캐시 적중 할인을 반영한다.

### 5.8 Notifier

| 항목 | 값 |
| --- | --- |
| **목적** | 인시던트 알림을 외부 채널로 발송한다 |
| **초안** | `AI-SVC` |
| **확정** | `AI-SVC` |
| **상태** | 설계 |
| **구현체** | `SlackWebhookNotifier`(기본) / `NullNotifier`(테스트·오프라인) |
| **소비자** | `src/drift/monitor.py`, `src/agent/loop.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기 / 비동기 |
| --- | --- | --- |
| `send` | 알림 1건을 발송한다 | sync |
| `channel` | 채널 식별자를 반환한다(속성) | sync |

#### `send`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `payload` | `NotificationPayload` | Y | 알림 내용 | `console_url`·`dedup_key` 필수 |

**반환값** `None` — 성공 시 아무것도 반환하지 않는다. 실패는 예외로 표현한다.

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `NotificationTransientError` | 429·5xx·타임아웃 — 재시도 대상 |
| `NotificationPermanentError` | 400(페이로드 오류)·404(Webhook 폐기) — 재시도 금지 |

**코드 예시**

```python
class Notifier(Protocol):
    @property
    def channel(self) -> str:
        """erd.md notifications.channel에 저장된다. NotificationChannel Enum 값."""
        ...

    def send(self, payload: NotificationPayload) -> None:
        ...
```

**구현 노트**

- **중복 발송 억제는 이 계층의 책임이 아니다.** 인시던트당 1회·쿨다운 판정은 호출자가 `notifications` 테이블로 처리한다(policies.md 3.6).
- 채널별 서식 변환은 구현체 내부에서 한다.
- 발송한 본문 스냅샷은 호출자가 `notifications.payload`에 저장한다.
- `NullNotifier`는 로컬 개발과 테스트에서 쓴다.

---

## 6. 예외 코드

모든 예외는 `src/interfaces/exceptions.py`에 정의하고 `PlatformError`를 상속한다.

| 예외 클래스 | 발원 인터페이스 | 발생 조건 | 호출자 대응 |
| --- | --- | --- | --- |
| `DetectorLoadError` | `Detector` | 모델 가중치·ONNX 파일 적재 실패 | 작업을 재시도 큐에 남기고 경보. **수집은 계속** |
| `DetectorInputError` | `Detector`, `Embedder` | 빈 입력, 배치 크기 초과, 빈 answer | 재시도 금지 → 즉시 FAILED |
| `DetectorInferenceError` | `Detector` | 추론 중 런타임 오류 | 백오프 재시도(최대 3회) |
| `EmbeddingError` | `Embedder` | 임베딩 모델 적재·추론 실패 | 로그 후 **임베딩 없이 진행** |
| `RoutingConfigError` | `Router` | τ·r이 0.0~1.0 범위를 벗어남 | 재시도 금지. **기동 시 설정 검증에서 먼저 걸러야 한다** |
| `DriftConfigError` | `DriftDetector` | 필수 설정 누락·범위 위반 | 재시도 금지. 해당 판정기 비활성화 후 경보 |
| `DriftInputError` | `DriftDetector` | `required_metric`에 필요한 필드 누락 | 해당 판정기만 건너뛰고 나머지 판정기로 진행 |
| `LLMRateLimitError` | `LLMClient`, `Judge` | 429 응답 | 백오프 재시도(1s→4s→16s, 최대 3회) |
| `LLMTransientError` | `LLMClient`, `Judge` | 5xx, 타임아웃, 연결 오류 | 동일 재시도 |
| `LLMPermanentError` | `LLMClient`, `Judge` | 400/401/403 | 재시도 금지. 경보 후 전파 |
| `BudgetExceededError` | `LLMClient`, `Judge` | 지출 한도 도달 | **2단계 채점 중단, 1단계 유지** |
| `JudgeParseError` | `Judge` | 채점 결과 구조화 실패 | 1회 재시도 후 실패 처리 |
| `PricingNotFoundError` | `CostCalculator` | 단가표에 모델 없음 | 재시도 금지. **0으로 대체하지 않는다** |
| `NotificationTransientError` | `Notifier` | 429·5xx·타임아웃 | 백오프 재시도(1s→5s→25s, 최대 3회) |
| `NotificationPermanentError` | `Notifier` | 400·404 | 재시도 금지. 인시던트 처리는 계속 진행 |

```python
class PlatformError(Exception):
    """플랫폼 공통 예외 기반 클래스. retryable 속성으로 호출자의 재시도 판단을 돕는다."""
    retryable: bool = False

# --- Detector / Embedder ---
class DetectorLoadError(PlatformError):
    """1단계 탐지 모델 적재 실패. 가중치·ONNX 파일이 없거나 손상된 경우."""
    retryable = True

class DetectorInputError(PlatformError):
    """검사 입력이 계약을 위반한 경우. 빈 리스트, 빈 answer, 배치 크기 초과."""
    retryable = False

class DetectorInferenceError(PlatformError):
    """추론 중 런타임 오류."""
    retryable = True

class EmbeddingError(PlatformError):
    """임베딩 모델 적재 또는 추론 실패."""
    retryable = True

# --- Router ---
class RoutingConfigError(PlatformError):
    """τ 또는 r이 0.0~1.0 범위를 벗어남. 기동 시 설정 검증에서 먼저 걸러야 한다."""
    retryable = False

# --- DriftDetector ---
class DriftConfigError(PlatformError):
    """필수 설정 누락 또는 범위 위반."""
    retryable = False

class DriftInputError(PlatformError):
    """required_metric에 필요한 필드가 WindowStats에 없음."""
    retryable = False

# --- LLMClient / Judge ---
class LLMRateLimitError(PlatformError):
    """LLM 제공자 호출량 제한. HTTP 429."""
    retryable = True

class LLMTransientError(PlatformError):
    """5xx, 타임아웃, 연결 오류."""
    retryable = True

class LLMPermanentError(PlatformError):
    """400/401/403. 재시도해도 달라지지 않는 오류."""
    retryable = False

class BudgetExceededError(PlatformError):
    """워크스페이스 또는 자체 지출 한도 초과."""
    retryable = False

class JudgeParseError(PlatformError):
    """채점 결과를 정해진 구조로 파싱하지 못함. 채점 프롬프트 문제로 기록한다."""
    retryable = True  # 1회 재시도 후 최종 실패

# --- CostCalculator ---
class PricingNotFoundError(PlatformError):
    """단가표에 모델이 없음. configs/pricing.yaml 갱신이 필요하다."""
    retryable = False

# --- Notifier ---
class NotificationTransientError(PlatformError):
    """429·5xx·타임아웃."""
    retryable = True

class NotificationPermanentError(PlatformError):
    """400(페이로드 오류)·404(Webhook 폐기)."""
    retryable = False
```

---

## 7. 제약 및 불변식

### 7.1 입력 제약

- 모든 문자열 파라미터는 빈 문자열(`""`)을 허용하지 않는다. 단 `EvalInput.contexts`는 **빈 리스트를 허용**한다.
- `None` 입력은 시그니처에서 `| None`으로 명시된 파라미터에만 허용한다.
- 배치 입력 크기 상한: `Detector` 16, `Judge` 50, `Embedder` 64. 초과 시 호출자가 분할한다.
- 시각 문자열은 **ISO 8601 UTC**(`2026-11-18T09:05:00Z`)만 허용한다.
- `WindowStats.window_start/end`는 `traces.started_at` 기준 창이어야 한다(erd.md 1장 창 집계 기준 원칙).
- 설정값(τ·r 범위, 임베딩 차원, "배치 대기 < 판정 창" 관계)은 **기동 시 검증**한다(policies.md 2.2).

### 7.2 출력 제약

- 메서드는 `None`을 반환하지 않는다. 결과가 없으면 빈 리스트를 반환한다(`Notifier.send`만 예외).
- 에러 상황은 반환값이 아닌 **예외**로 표현한다.
- 배치 메서드는 **입력과 같은 길이·같은 순서**의 결과를 반환한다.
- 부분 실패를 표현해야 하면 예외를 던지고 호출자가 배치를 쪼개 재시도한다.
- 구현체는 입력 객체를 변경하지 않는다.

### 7.3 성능 제약

| 인터페이스 | 제약 | 비고 |
| --- | --- | --- |
| `Detector.detect_batch` | vhp-4c-8gb 4 vCPU에서 배치 16건 기준 p95 측정·보고 | 목표치는 서버 1차 측정(SP3) 후 확정 |
| `Embedder.embed_batch` | 64건 기준 1초 이내 | CPU 로컬 실행 |
| `Router.route` | 1,000건 기준 10ms 이내 | 순수 계산. I/O 없음 |
| `DriftDetector.judge` | 창 1개 기준 100ms 이내 | 통계 계산만 수행 |
| `LLMClient.complete` | 타임아웃은 policies.md 2.1 참조(생성 30초, 채점·에이전트 60초) | — |
| 공통 | 생성자(모델 적재) 시간은 성능 제약에서 제외. 지연 측정은 예열 후 수행 | — |

### 7.4 불변식

```
[항상 참] DetectionResult.score: 0.0 <= score <= 1.0 (높을수록 환각 의심 — stage 1)
[항상 참] JudgeResult.score: 0.0 <= score <= 1.0 (높을수록 품질 좋음 — stage 2)
[항상 참] 두 score의 방향이 반대이므로 직접 비교하지 않는다
[항상 참] 배치 메서드: len(결과) == len(입력)
[항상 참] 배치 메서드: 결과[i].trace_id == 입력[i].trace_id
[항상 참] HallucinationSpan: 0 <= start < end <= len(answer)
[항상 참] HallucinationSpan: text == answer[start:end]
[항상 참] RoutingDecision: to_stage2 == True  <=> reason in ("threshold", "sample")
[항상 참] RoutingDecision: to_stage2 == False <=> reason == "none"
[항상 참] score >= threshold인 건의 reason은 항상 "threshold" (표본 추첨보다 우선)
[항상 참] DriftVerdict: deferred == True이면 is_drift == False이고 drift_score is None
[항상 참] Embedder가 반환한 모든 벡터의 길이 == Embedder.dimension
[항상 참] Embedder가 반환한 벡터의 L2 norm == 1.0 (정규화)
[항상 참] CostCalculator.calculate() 반환값 >= 0.0
[항상 참] TokenUsage의 모든 필드 >= 0
[항상 참] Detector.name은 "{모델명}-{서빙형식}" 형식, 100자 이내
[항상 참] DriftDetector.name은 DriftDetectorName Enum 값 중 하나
[항상 참] 구현체는 같은 입력에 대해 같은 출력을 낸다
         (LLMClient와 Router의 sample 추첨 제외 — 후자는 시드 고정 시 결정적)
[항상 참] WindowStats의 시간 기준은 traces.started_at
```

---

## 8. 계약 변경 규칙

- `src/interfaces/`는 `CODEOWNERS` 승인 필수 경로다(ADR-009).
- **계약 변경과 양쪽 구현 수정을 한 PR에서** 처리한다(ADR-024).

| 변경 유형 | 예시 | 처리 |
| --- | --- | --- |
| 하위 호환 (추가) | 선택 파라미터 추가, `NotRequired` 필드 추가 | 버전 마이너 증가, 상태 유지 |
| 비호환 (변경·삭제) | 반환 타입 변경, 필수 파라미터 추가, Enum 값 삭제 | 버전 마이너 증가 + 변경 이력에 비호환 표시, 양쪽 구현·테스트 동시 수정 |
| Enum 값 추가 | `DriftDetectorName`에 판정기 추가 | 이 문서 2.2 + erd.md 8장 CHECK 제약 + DB 마이그레이션을 같은 PR에서 수정 |
- **SP3 주입 실험 중에는 집계에 영향을 주는 계약을 변경하지 않는다.**

---

## 9. 테스트 계약

### 9.1 더미 구현체

| 인터페이스 | 더미 구현 | 용도 |
| --- | --- | --- |
| `Detector` | `StubDetector` — 고정 점수·빈 구간 반환 | 모델 학습 전 파이프라인 완성 |
| `Judge` | `StubJudge` — 고정 점수·이유 반환 | LLM 호출 없이 워커 테스트 |
| `DriftDetector` | `AlwaysDriftDetector` / `NeverDriftDetector` | 인시던트 생성·알림 경로 테스트 |
| `Embedder` | `ZeroEmbedder` — 0 벡터 반환 | 임베딩 없이 통합 테스트 |
| `LLMClient` | `RecordedLLMClient` — 녹화된 응답 재생 | 비용 없이 에이전트 루프 테스트 |
| `Notifier` | `NullNotifier` / `CapturingNotifier` | 발송 없이 호출 여부 검증 |

더미 구현체는 `src/interfaces/stubs.py`에 두고 계약 테스트의 대상으로도 쓴다.

### 9.2 계약 테스트

- 모든 구현체는 7.4의 불변식을 검사하는 공통 계약 테스트를 통과해야 한다.
- 검사 항목: 길이·순서 보존, 점수 범위 및 방향, span 오프셋 정합, 예외 `retryable` 분류, 입력 불변성.
- `Router`는 TDD 대상이다. 경계값(τ=0.0/1.0, r=0.0/1.0)과 표본 비율 수렴을 먼저 작성한다.
- `CostCalculator`는 단가표 기반 계산값과 실제 청구액을 1회 이상 대조해 오차를 보고한다(ADR-025).
- 새 구현체를 추가할 때 계약 테스트만 통과하면 설정 변경으로 교체 가능해야 한다.

---

## 미결 사항

- [x]  `Detector.detect_batch`의 배치 크기 상한 — 결정: 16 (A). vhp-4c-8gb 측정 후 상향은 하위 호환 변경
- [x]  `HallucinationSpan.confidence` 포함 여부 — 결정: 제거 (B). 출력 가능 시점에 하위 호환으로 추가
- [ ]  `DriftDetector.config`의 키 이름 표준화 (담당 `AI-MDL`, 기한 SP3)
- [ ]  `WindowStats.embeddings` 전달 방식 — 창 하나에 수백 개 벡터를 메모리로 넘기는 구조가 적절한지. 요약 통계(중심·분산)만 넘기는 안을 검토 (담당 `BOTH`, 기한 SP3)
- [ ]  `Judge` 교차 검증 구현체의 제공자 — 타 제공자 키 확보 여부에 달려 있다 (담당 `AI-MDL`, 기한 B-1 회신 후)
- [ ]  `LLMClient.complete_with_tools` 반환 구조 — `dict` 대신 `TypedDict` 2종 유니온으로 정의할지 (담당 `AI-SVC`, 기한 SP3 에이전트 구현 시)

---

end.