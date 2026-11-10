# 데이터셋 정의 v1.0

| 항목 | 값 |
| --- | --- |
| **상태** | 초안 |
| **날짜** | 2026-10-26 |
| **작성자** | `BOTH` |
| **관련** | ADR-016 (서비스 언어 영어), ADR-027 (탐지 모델 선택), ADR-028 (개선 축), ADR-029 (드리프트 탐지), `docs/experiments/protocol.md` (분할·시드) |

---

## 1. 데이터 한눈에 보기

| 데이터 | 과제 | 용도 |
| --- | --- | --- |
| RAGTruth | A, B-2 | 환각 탐지 모델 학습·평가, 라우팅 정확도 유지율 측정 |
| MT-Bench Human Judgments | B-1 | 채점자–사람 일치도 검증 |
| MS MARCO | C, D (+ A 추가 평가) | 실험용 RAG 코퍼스·고정 질문 집합 |
| 시연용 코퍼스 | 시연 전용 | 청중이 답의 정오를 직접 판단할 수 있는 영어 공개 기술 문서. 실험 지표 산출에 쓰지 않는다. (출처 확정 후 기재) |
| 주입 실험 데이터 | C, D | 팀 자체 생성 (`docs/experiments/injection-scenarios.md`) |
- 서비스 언어는 영어로 결정되었다(ADR-016). 모든 데이터셋이 영어이므로 학습 분포와 평가 분포가 일치한다.
- 시연용 코퍼스와 실험용 코퍼스는 분리하여 운영한다. 실험 지표가 시연 결과에 의존하지 않게 하기 위함이다.

---

## 2. 로컬 저장 경로 규칙

```
model/src/data/
  raw/{dataset}/          # 다운로드 원본 그대로. 수정 금지
    SOURCE.txt            # 출처 URL, 커밋/리비전, 다운로드 날짜, 담당자
  processed/{dataset}/    # 전처리 결과. 스크립트로만 생성
```

- `model/src/data/raw/`, `model/src/data/processed/`는 Git에 올리지 않는다(`.gitignore`). 다운로드·전처리 스크립트만 커밋한다.
    - `model/src/data/download_{dataset}.py`
    - `model/src/data/preprocess_{dataset}.py`
- 전처리 결과 형식은 JSONL. 같은 스크립트를 다시 돌리면 같은 결과가 나와야 한다(시드 고정).
- 원본 데이터는 저장소·공개 저장소·Hugging Face Hub에 재배포하지 않는다.

---

## 3. 데이터셋별 상세

### 3.1 RAGTruth

| 항목 | 내용 |
| --- | --- |
| **라이선스** | MIT |
| **언어** | 영어 |
| **규모** | RAG 응답 17,790건, 환각이 단어 단위로 사람 라벨링 |
| **과제 유형** | QA / Summary / Data2txt |
| **관련 ADR** | ADR-027 (탐지 모델 학습·평가) |

**다운로드:** GitHub `ParticleMedia/RAGTruth`의 `dataset/` 폴더 (`response.jsonl`, `source_info.jsonl`). 공식 배포처인 GitHub 원본을 기준으로 한다(제3자가 Hugging Face에 올린 사본은 쓰지 않음).

**`response.jsonl` 주요 필드:**

| 필드 | 설명 |
| --- | --- |
| `id`, `source_id`, `model`, `temperature` | 식별자·생성 조건 |
| `labels` | `[{text, start, end, label_type, meta, due_to_null, implicit_true}]` |
| `split` | `train` / `test` (공식 분할) |
| `quality` | 응답 품질 플래그 (`incorrect_refusal`, `truncated` 등) |
| `response` | 응답 본문 |

**전처리 절차:**

1. `response.jsonl`과 `source_info.jsonl`을 `source_id`로 조인한다.
2. 환각 라벨을 답변 기준 문자 오프셋 `[{start, end, label_type}]`으로 정규화한다.
3. 공식 `split`으로 train / test 분리 → train에서 `source_id` 단위로 dev 10% 분리(시드 42, 비율은 제안값).
4. 모델 입력 형식(문맥·질문·답변·단어별 라벨)으로 변환한다.
5. 검증: LettuceDetect 저장소의 전처리 결과와 건수·라벨 수를 대조한다.

**라벨 처리 규칙 (LettuceDetect 전처리 코드 확인 후 확정):** `implicit_true` 구간도 환각으로 본다. `quality`가 `incorrect_refusal`·`truncated`인 응답도 빼지 않는다. LettuceDetect가 같은 방식으로 처리하므로 기준선과 비교가 공정하다. 설정값은 `model/configs/data/ragtruth.yaml`에 있다.

**점수 방향 주의:** 학습 라벨은 환각 구간 = 1(positive), 정상 구간 = 0(negative)으로 설정한다. 이렇게 해야 모델 출력(stage 1 `score`)이 "높을수록 환각 의심"이 되어 라우팅 규칙 `score >= τ`와 일치한다(erd.md 1장 점수 방향 원칙, ADR-027 후속 작업).

**저장 경로:** `model/src/data/raw/ragtruth/`, `model/src/data/processed/ragtruth/{train,dev,test}.jsonl`

---

### 3.2 MT-Bench Human Judgments

| 항목 | 내용 |
| --- | --- |
| **라이선스** | CC BY 4.0 (출처 표기 필요) |
| **언어** | 영어 |
| **규모** | 질문 80개, 6개 모델 응답에 대한 전문가 쌍 비교 약 3,300건(`human`)과 GPT-4 판정(`gpt4_pair`) |
| **관련 ADR** | ADR-028 (과제 B: 채점자 신뢰도 검증) |

**다운로드:**

```python
from datasets import load_dataset
ds = load_dataset("lmsys/mt_bench_human_judgments", revision="<커밋 해시 고정>")
# splits: "human", "gpt4_pair"
```

**전처리 절차:**

1. 판정을 {A 승, B 승, 무승부}로 통일한다.
2. `(question_id, model_a, model_b, turn)` 키로 사람 판정을 묶는다. 같은 쌍에 평가자가 여럿이면 사람 간 일치율 계산용으로 표시한다.
3. `question_id` 단위로 프롬프트 조정용 20% / 보고용 80% 분리(시드 42, 비율은 제안값).

**저장 경로:** `model/src/data/raw/mt_bench/`, `model/src/data/processed/mt_bench/{tune,report}.jsonl`

**주의:** 영어 일반 대화 중심 선호 비교 데이터이므로 결과를 이 서비스에 그대로 일반화하지 않는다. 여력이 있으면 자체 데이터 일부에 사람 라벨을 달아 보완 검증한다.

---

### 3.3 MS MARCO

| 항목 | 내용 |
| --- | --- |
| **라이선스** | Microsoft 이용 약관: 비상업적 연구 목적 전용 |
| **언어** | 영어 |
| **관련 ADR** | ADR-028 (과제 C·D 실험 질문 집합), ADR-027 (과제 A 추가 평가) |

**선택 근거:** RAGTruth의 QA 과제가 MS MARCO를 출처로 하므로, 1단계 탐지 모델의 학습 분포와 맞는 조건에서 주입 실험을 수행할 수 있다.

**다운로드:** Hugging Face `microsoft/ms_marco` / 공식 안내 `microsoft.github.io/msmarco`

- config는 `v1.1`(약 10만 행, 다운로드 약 169MB)과 `v2.1`(약 101만 행, 약 1.38GB)이 있다. v1.1로 시작하는 것을 제안한다.
- 주요 필드: `query`, `query_id`, `query_type`, `passages`(`is_selected`, `passage_text`, `url`), `answers`, `wellFormedAnswers`

**전처리 — 질문 집합 `msmarco_eval_v1` (AI-MDL, 10/28 주 일정):**

1. 정답이 있는 질문만 사용한다. `answers`가 비어 있는 질문은 제외하고, 그 밖의 "답 없음" 표기 방식은 실제 데이터를 열어 확인한 뒤 규칙을 정한다.
2. RAGTruth QA에 쓰인 질문과 겹치는 질문을 제외한다. 탐지 모델이 학습 때 본 질문으로 평가하면 성능이 부풀려지기 때문이다.
3. 질문은 LLM으로 생성하지 않고 원문 그대로 쓴다(편향 통제).
4. 시드 42로 표본 추출. 질문 수는 트래픽 계획(0.5 rps × 90분 ≈ 2,700건 요청)에 맞춰 정한다.

**전처리 — 코퍼스 (AI-SVC, pgvector에 적재):**

- 선택한 질문들의 후보 문단(passages) 전체를 코퍼스로 사용한다. 청크 분할·임베딩은 RAG 서비스 설정(`configs/`)을 따른다.

**저장 경로:** `model/src/data/raw/ms_marco/`, `model/src/data/processed/ms_marco/{questions_eval_v1.jsonl, corpus.jsonl}`

---

## 4. 라이선스 확인 사항

| 데이터·모델 | 라이선스 / 이용 조건 | 확인 상태 |
| --- | --- | --- |
| RAGTruth | MIT | GitHub 저장소 확인 (2026-10-24) |
| MT-Bench Human Judgments | CC BY 4.0, 출처 표기 필요 | HF 카드 확인 (2026-10-24) |
| MS MARCO | Microsoft 이용 약관: 비상업적 연구 목적 전용 | 약관 확인 |
| all-MiniLM-L6-v2 | Apache-2.0 | HF 모델 카드 확인 (2026-10-24) |
| LettuceDetect (`lettucedect-base-modernbert-en-v1`) | MIT | HF 모델 카드 확인 (2026-10-24) |
| 시연용 코퍼스 | 오픈 라이선스 문서로 선정 예정 | 미결 (미결 A-4) |
- **MS MARCO:** 비상업 연구 목적이므로 학술 프로젝트·논문 사용은 가능하나, 서비스를 상업적으로 쓰는 것처럼 보이게 하지 않는다. 시연은 별도 시연용 코퍼스를 쓰므로 이 문제를 피한다.
- **발표 자료·논문:** 각 데이터셋 인용(bibtex)과 라이선스 표기를 넣는다.

---

## 미결 사항

- [ ]  각 데이터셋 다운로드 리비전(커밋 해시) 고정 후 이 문서에 기록
- [x]  RAGTruth `implicit_true`·`quality` 필드 처리 규칙 확정 (LettuceDetect 전처리 코드 참조) → 3장 라벨 처리 규칙
- [ ]  RAGTruth QA와 MS MARCO 질문 겹침 확인 방법 (질문 문자열 정규화 후 일치 검사)
- [ ]  MT-Bench 프롬프트 조정용/보고용 분할 비율 확정 (현재 20/80 제안값)
- [ ]  MS MARCO v1.1 질문 수 확정 (트래픽 계획 확정 후)
- [ ]  시연용 코퍼스 선정 (공동, 미결 A-4)

---

end.