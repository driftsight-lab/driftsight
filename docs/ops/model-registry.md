# 모델 가중치 관리

- 관련: ADR-023 (ONNX 서빙), ADR-027 (탐지 모델 선택·교체 기준), ADR-028 (개선 축 = 추론 효율), `docs/policies.md` (비밀값 관리, `HF_TOKEN`)

---

## 1. 원칙

- 모델 가중치는 git 저장소에 넣지 않는다. Hugging Face Hub에 두고 서빙 시 받는다.
- 서빙 시 항상 리비전(커밋 해시 또는 태그)을 고정해서 받는다. `main`을 그대로 받지 않는다.
    - 이유: 외부 모델이 업데이트되면 1단계 점수 분포가 바뀐다. 우리가 잡으려는 "변경 때문에 생기는 품질 저하"가 우리 쪽에서 발생하는 셈이 된다(SCN-002 시나리오와 동일 현상).
- 1단계 탐지 모델 버전은 `evaluations.evaluator_key`에, 임베딩 모델 버전은 `embeddings.model_name`에 기록한다.
    - `evaluator_key` 형식: `{모델명}-{버전}-{서빙형식}` — 버전을 포함해야 같은 아키텍처의 v0.1.0 / v0.2.0을 같은 트레이스에서 비교할 수 있다.
    예) `lettucedetect-modernbert-base-onnx-int8`, `halludetect-modernbert-base-v0.1.0-onnx-int8`
    - `model_name` 형식: HF 저장소 슬러그와 리비전을 모두 담는다.
    예) `sentence-transformers/all-MiniLM-L6-v2@cf4be3cb`
    - 두 컬럼 모두 ERD v1.0 5장에 정의되어 있다. `model_version`이라는 컬럼은 ERD에 없으므로 사용하지 않는다.

---

## 2. 관리 대상 모델

| 용도 | 저장소 | 형식 | 비고 |
| --- | --- | --- | --- |
| 1단계 기준선·임시 모델 | `KRLabsOrg/lettucedect-base-modernbert-en-v1` (외부) | PyTorch + ONNX INT8 | 자체 모델 완성 전 1단계 구동 (ADR-027) |
| 1단계 자체 모델 | `aisv-team17/halludetect-{backbone}` (우리) | PyTorch + ONNX FP32 + ONNX INT8 | 과제 A 결과 |
| 응답 임베딩 | `sentence-transformers/all-MiniLM-L6-v2` (외부) | ONNX (CPU 서빙, ADR-023) | 384차원 |

각 외부 모델의 고정 리비전은 `.env.example`에 키 이름으로, 실제 해시는 5장 표에 기록한다.

---

## 3. 우리 모델 업로드·버전 태그 규칙

### 3.1 저장소

- HF Organization: `aisv-team17` (private), 생성 필요, 두 사람 모두 쓰기 권한
- 이름: `aisv-team17/halludetect-{backbone}` 예) `halludetect-modernbert-base`, `halludetect-deberta-v3-small`
- 저장소 내 폴더 구성

```
pytorch/          # model.safetensors + config.json + 토크나이저 파일
onnx-fp32/        # model.onnx + config.json + 토크나이저 파일
onnx-int8/        # 양자화된 model.onnx + config.json + 토크나이저 파일
README.md         # 모델 카드
```

> 각 폴더는 그 폴더만 받아도 로드할 수 있어야 한다. 서빙 시 `allow_patterns`로 한 폴더만 받기 때문에(4장), 토크나이저·config 파일을 `pytorch/`에만 두면 ONNX 형식으로 서빙할 때 로드에 실패한다.
> 

업로드 후 확인: 빈 캐시에서 4장 절차로 형식별로 한 번씩 받아 실제 로드되는지 확인한다.

### 3.2 업로드 조건

1. `docs/experiments/log.md`에 기록되고 상태가 `완료`인 실험의 모델만 올린다.
2. 같은 test 지표가 `experiments/results/A/.../metrics.json`에 있어야 한다.

### 3.3 버전 태그 `v{major}.{minor}.{patch}`

| 올리는 경우 | 예 |
| --- | --- |
| major: 백본 또는 입력 형식 변경 | 입력에 질문을 넣는 방식 변경 |
| minor: 재학습·하이퍼파라미터 변경으로 성능이 바뀜 | 학습률 변경 후 재학습 |
| patch: 성능 변화 없는 변경 | 모델 카드 수정, ONNX 재변환(같은 가중치) |

### 3.4 모델 카드 필수 항목

- 학습 데이터·분할(RAGTruth train/dev 분리 시드), 학습 설정, 시드
- test 지표: 응답 단위 F1, 토큰 단위 F1, 크기(MB), **Vultr vhp-4c-8gb CPU p95 지연** (형식별)
- 연결 정보: `log.md` 항목 날짜, git commit, `experiments/configs/` 경로
- 한계: 영어 전용, RAGTruth 분포 기준

### 3.5 업로드 예

```bash
hf upload aisv-team17/halludetect-modernbert-base ./out . \
  --commit-message "v0.1.0: ModernBERT-base on RAGTruth (s42)"

hf repos tag create aisv-team17/halludetect-modernbert-base v0.1.0
```

> `huggingface_hub` 공식 CLI 명령은 `hf`. 예전 버전은 `huggingface-cli`를 썼으므로 `uv.lock`의 버전 확인 필요.
> 

---

## 4. 서빙 시 다운로드 절차

**1. 환경변수로 저장소·리비전·형식 지정**

```bash
# .env에서 설정 (키 이름만 .env.example에, 값은 5장 표에서 확인)
DETECTOR_REPO=KRLabsOrg/lettucedect-base-modernbert-en-v1  # SP2 기준
DETECTOR_REVISION=<커밋 해시>   # 5장 표에서 확인 — main 금지
DETECTOR_FORMAT=onnx-int8       # pytorch | onnx-fp32 | onnx-int8
EMBEDDING_REPO=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_REVISION=<커밋 해시>  # 5장 표에서 확인
HF_HOME=/models/hf-cache
HF_TOKEN=                       # private 저장소용. 값은 문서·코드에 쓰지 않음
```

**2. 워커 기동 시 다운로드**

```python
from huggingface_hub import snapshot_download

path = snapshot_download(
    repo_id=DETECTOR_REPO,
    revision=DETECTOR_REVISION,
    allow_patterns=[f"{DETECTOR_FORMAT}/*"],   # 필요한 형식만 받음
    cache_dir=HF_HOME,
)
```

**3. 캐시 볼륨**

캐시는 Docker 볼륨(`models:/app/models`)에 두어 재기동 때 다시 받지 않는다.
`docker-compose.yml`에 이미 반영됨:

```yaml
worker:
  volumes:
    - models:/app/models

volumes:
  models:
```

**4. evaluator_key·model_name 구성**

```python
# evaluations.evaluator_key — 같은 아키텍처의 버전 비교를 위해 리비전 포함
evaluator_key = f"halludetect-modernbert-base-{DETECTOR_REVISION}-{DETECTOR_FORMAT}"
# 예: "halludetect-modernbert-base-v0.1.0-onnx-int8"

# embeddings.model_name — 저장소 슬러그@리비전
model_name = f"{EMBEDDING_REPO}@{EMBEDDING_REVISION}"
# 예: "sentence-transformers/all-MiniLM-L6-v2@cf4be3cb"
```

> **ERD 정합 주의**: `evaluations.evaluator_key`와 `embeddings.model_name`이 올바른 컬럼명이다. `model_version`이라는 컬럼은 ERD에 없다(ERD v1.0 5장).
> 

**5. 다운로드 실패 처리**

다운로드 실패 시 워커는 기동을 멈춘다. 잘못된 모델로 조용히 검사하는 것보다 낫다.
장애 대응은 `docs/ops/runbook.md §3.6`.

**6. 다운로드 후 무결성 검증**

```python
import onnxruntime as ort

# ONNX 모델 로드 검증
sess = ort.InferenceSession(f"{path}/model.onnx", providers=["CPUExecutionProvider"])
print("입력 노드:", [n.name for n in sess.get_inputs()])
print("출력 노드:", [n.name for n in sess.get_outputs()])

# 더미 입력으로 추론 테스트
import numpy as np
dummy = {"input_ids": np.zeros((1, 16), dtype=np.int64),
         "attention_mask": np.ones((1, 16), dtype=np.int64)}
output = sess.run(None, dummy)
assert output[0].shape[0] == 1, "추론 출력 형상 오류"
print("무결성 검증 통과")
```

---

## 5. 고정 리비전 기록

| 모델 | 저장소 | 리비전 | 고정한 날짜 | 고정한 사람 |
| --- | --- | --- | --- | --- |
| LettuceDetect base | `KRLabsOrg/lettucedect-base-modernbert-en-v1` | `bbd77832f52f9bd87546a3924c032467921f5c34` | 2026-11-10 | 장희현 |
| all-MiniLM-L6-v2 | `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | 2026-11-10 | 장희현 |
| halludetect-* | `aisv-team17/halludetect-{backbone}` | (첫 업로드 후) |  |  |

> 리비전 없이 `main`을 받으면 1장 원칙을 위반한다. SP2 워커 구현 전에 반드시 채운다.
> 

**리비전 확인 방법:**

```python
from huggingface_hub import model_info

# 현재 main 브랜치의 커밋 해시 확인
info = model_info("KRLabsOrg/lettucedect-base-modernbert-en-v1")
print(info.sha)   # 이 값을 DETECTOR_REVISION에 고정

info = model_info("sentence-transformers/all-MiniLM-L6-v2")
print(info.sha)   # 이 값을 EMBEDDING_REVISION에 고정
```

---

## 6. 모델 교체 절차 (LettuceDetect → 자체 모델 등)

1. 과제 A 평가를 같은 평가 코드로 실행해 `log.md`에 기록한다.
2. **ADR-027**의 교체 기준(F1 손실 허용 범위 안 + CPU p95 지연 또는 모델 크기 감소)을 충족하는지 확인한다. 손실 허용 범위는 SP2 1차 실험 후 두 파트가 정확도–효율 곡선을 보고 합의한다.
3. 환경변수 변경 PR → 상대 담당자 승인 (CODEOWNERS 핵심 경로)
4. **교체 시점을 서비스 파트에 공유**: 1단계 점수 분포가 바뀌므로 드리프트 기준을 다시 잡아야 한다. 그렇지 않으면 모델 교체 자체가 드리프트로 잡힌다.
5. **`version_changes` 기록**: 모델 교체는 `versions.kind='model'`로 새 버전을 등록하고 `version_changes`에 `source='deploy'`로 남긴다.
    - 이유: 모델 교체 이후 드리프트가 발생했을 때 원인 분석 에이전트가 "모델 교체"를 원인 후보로 지목할 수 있다. 기록하지 않으면 에이전트가 탐지하지 못한다.
    - ERD 영향: `versions.kind` CHECK 제약에 `model` 값 추가 + DB 마이그레이션 필요 (ADR-022, ERD 8장 코드값 테이블 동시 수정)
    - 담당: `AI-SVC`

**교체 실패 시 롤백:**

```bash
# 환경변수를 이전 리비전으로 되돌리고 PR → 재배포
# .env에서 DETECTOR_REVISION을 이전 값으로 변경
# docker compose exec worker python -m src.worker.main 재시작
docker compose restart worker
docker compose logs -f worker | grep "evaluator_key"
# 이전 evaluator_key가 출력되면 롤백 완료
```

---

## 확인 필요 (TODO)

- [ ]  HF Organization(`aisv-team17`) 생성, 팀원 초대 — **SP2 시작 전 필수**
- [x]  외부 모델 리비전 고정 후 5장 표 기입 — **SP2 워커 구현 전 필수**
    - LettuceDetect base (`KRLabsOrg/lettucedect-base-modernbert-en-v1`)
    - all-MiniLM-L6-v2 (`sentence-transformers/all-MiniLM-L6-v2`)
- [x]  모델 교체를 `version_changes`에 기록할지 결정 → **기록하기로 결정** (6장 5단계 참고)
    - `versions.kind='model'` 추가, ERD 8장·마이그레이션 수정 필요
- [x]  모델 캐시 볼륨 → `docker-compose.yml` `models` 볼륨 반영 완료 (`AI-SVC`)

---

end.