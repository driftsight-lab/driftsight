# ADR-003: 백엔드 언어·프레임워크로 Python(FastAPI)을 사용한다

| 항목 | 값 |
| --- | --- |
| 상태 | 수락됨 |
| 날짜 | 2026-10-14 |
| 작성자 | `AI-SVC` |
| 검토자 | `AI-MDL` |
| **갱신** | 2026-11-16 — 인프라 Vultr vhp-4c-8gb 전환(ADR-014)에 따라 서버 표기 수정. 결정 내용은 변경 없음 |

---

## 컨텍스트

플랫폼은 수집 API, 비동기 검사 워커, 모델 추론 서빙, MCP 서버, 조회 API를 한 서버(Vultr vhp-4c-8gb, 4 vCPU·8GiB) 안에서 모두 돌려야 한다. 특히 1단계 탐지 모델 서빙과 `AI-MDL` 파트가 작성한 학습·평가 코드를 그대로 연동해야 하며, MCP SDK와 OTel GenAI 계측도 함께 필요하다. 학과 수업에서 다룬 백엔드 스택은 Spring Boot이므로 익숙함만 보면 JVM 쪽이 유리하다.

## 결정 근거

- 모델 추론·계측·MCP 생태계와의 연동 비용.
- 두 파트 간 코드 이동 비용(모델 파트 산출물의 재사용 가능성).
- 단일 서버에서의 메모리 사용량.
- 팀 학습 비용.

## 고려한 옵션들

- 옵션 1: Spring Boot (Java/Kotlin)
- 옵션 2: Python + FastAPI
- 옵션 3: 분리 운영 — API는 Spring Boot, 추론 워커만 Python

## 결정

옵션 2 **Python + FastAPI**를 선택한다. ONNX Runtime·Transformers·OTel GenAI 계측·MCP Python SDK가 모두 Python을 우선 지원하므로 `AI-MDL`이 만든 `Detector`·`DriftDetector` 구현체를 변환 없이 그대로 플러그인할 수 있고, 2 vCPU·8GiB 단일 서버에서 JVM과 Python 런타임을 동시에 띄우는 메모리 부담을 피할 수 있다. 수업 스택과 다르다는 점은 감수하되, 학습 비용은 FastAPI의 단순한 모델로 상쇄된다.

## 결과

**긍정적**

- 모델 파트의 학습·평가 코드와 서빙 코드가 같은 언어라 인터페이스 계약(ADR-024)만 맞추면 바로 붙는다.
- 추론 프로세스를 별도 서비스로 분리하지 않아 컨테이너 수와 메모리를 절약한다.
- Pydantic 기반 스키마로 Ingest API 검증과 Swagger 문서가 자동 생성된다.

**부정적**

- 수업에서 다룬 JVM 백엔드 경험을 이 프로젝트로는 쌓지 못한다.
- GIL 특성상 CPU 바운드 추론은 워커 프로세스 분리로 다뤄야 한다.

**후속 작업**

- 추론 워커를 별도 프로세스로 기동하는 Docker Compose 구성 (T1-08)
- DB 접근 방식(async 드라이버 또는 스레드풀) 확정

---

## 옵션별 장단점

### 옵션 1 — Spring Boot

- 장점: 팀이 수업에서 다뤄 익숙하고, 취업 포트폴리오에서 수요가 크다.
- 단점: ONNX·Transformers·MCP 연동에 추가 브리지가 필요해 모델 파트 산출물을 그대로 쓸 수 없다.
- 단점: JVM 힙이 단일 서버 메모리 예산(8GiB)에서 큰 비중을 차지한다.

### 옵션 2 — Python + FastAPI (채택)

- 장점: 추론·계측·에이전트 생태계가 모두 Python 우선이다.
- 장점: 모델 파트와 서비스 파트가 같은 언어를 써 리뷰와 코드 이동이 쉽다.
- 단점: 정적 타입 보장과 동시성 처리는 JVM보다 약하다(타입 힌트 + 프로세스 분리로 완화).

### 옵션 3 — 분리 운영 (Spring + Python 워커)

- 장점: 수업 스택을 유지하면서 추론은 Python으로 처리할 수 있다.
- 단점: 런타임 두 개, 통신 계층 하나가 늘어 단일 서버 자원과 8주 일정 양쪽에 부담이 된다.

## 연관 ADR

- Related to ADR-010 (의존성 관리)
- Related to ADR-014 (단일 서버 인프라)
- Refined by ADR-023 (추론 런타임)
- Related to ADR-027 (모델 파트 코드 직접 연동)

## 참조

- FastAPI 공식 문서, ONNX Runtime Python API, MCP Python SDK

---

end.