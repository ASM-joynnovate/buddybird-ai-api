# buddybird-ai-api

Python 3.12와 uv로 gRPC 서버를 실행하고 헬스체크를 확인하는 프로젝트다.
현재 제공하는 서비스는 gRPC 표준 헬스체크 `grpc.health.v1.Health`다. onset 분석 RPC `OnsetService.AnalyzeSession`은 앵무 소리 판정 모델과 onset 분석으로 캡처마다 위급 여부를 돌려준다.

## 준비

- 준비 환경: Python 3.12, uv, make
- 명령 실행 위치: 저장소 최상위 디렉터리

의존성을 설치하고 커밋 전 검사 훅을 등록한다.

```sh
make setup
```

`make setup`은 `uv sync`를 실행하고 git `core.hooksPath`를 `.githooks`로 지정한다.
등록한 훅은 커밋할 Python 파일에 `ruff check --fix`와 `ruff format --check`를 실행한다.

## 실행

개발 서버를 실행한다. 포트 기본값은 50051이다.

```sh
make local
make local port=50052
```

별도 터미널에서 헬스체크를 호출한다. 서버와 같은 포트를 지정한다.

```sh
make health
make health port=50052
```

서버가 요청을 받을 수 있으면 `SERVING`을 출력한다.

| 항목 | 값 |
| --- | --- |
| 헬스체크 서비스 | `grpc.health.v1.Health` |
| 전체 상태 서비스 이름 | 빈 문자열 |
| 포트 환경 변수 | `GRPC_PORT`, 기본값 50051 |
| 로그 수준 환경 변수 | `LOG_LEVEL`, 기본값 `INFO` |

- 헬스체크 검사 범위: 서버 응답만 확인, 분석 준비 상태와 외부 서비스 연결 상태는 미검사
- 서버 종료: `Ctrl+C`
  - `SIGINT`, `SIGTERM` 수신 시 헬스체크 상태 `NOT_SERVING`으로 변경
  - 처리 중인 요청을 최대 10초 기다린 뒤 종료

### 헬스체크 명령

컨테이너 헬스체크에서도 같은 명령을 사용한다.

```sh
python -m core.grpc.healthcheck --target 127.0.0.1:50051
```

| 옵션 | 기본값 |
| --- | --- |
| `--target` | `127.0.0.1:<GRPC_PORT>` |
| `--service` | 빈 문자열 |
| `--timeout` | 3초 |

- 종료 코드 0: `SERVING`
- 종료 코드 1: 연결 실패, 제한 시간 초과, `SERVING` 외 상태

## 오류 응답

`ErrorInterceptor`가 `CustomError`와 처리하지 않은 예외를 gRPC 상태로 변환한다.

- 상태 메시지: 예외의 `message`
- 상세 정보: `google.rpc.ErrorInfo` 1개
  - `reason`: 예외의 `error_code`
  - `domain`: `buddybird-ai-api`
- 예외의 `detail`: 응답에 미포함

| 상황 | gRPC 상태 | `reason` |
| --- | --- | --- |
| `CustomError` code 400, 422 | `INVALID_ARGUMENT` | 예외에 지정한 값 |
| `CustomError` code 404 | `NOT_FOUND` | 예외에 지정한 값 |
| `CustomError` code 500 | `INTERNAL` | 예외에 지정한 값 |
| `CustomError` 그 외 code | - 500 이상: `INTERNAL`<br>- 500 미만: `INVALID_ARGUMENT` | 예외에 지정한 값 |
| 처리하지 않은 예외 | `INTERNAL` | `COMMON__INTERNAL_SERVER_ERROR` |

처리하지 않은 예외는 서버 로그에 예외 내용을 기록한다.
응답 메시지는 `서버 내부 오류가 발생했습니다. 관리자에게 문의해주세요.`로 고정한다.

클라이언트는 `ErrorInfo`를 아래 방식으로 읽는다.

```python
from google.rpc import error_details_pb2
from grpc_status import rpc_status

status = rpc_status.from_call(error)
info = error_details_pb2.ErrorInfo()
status.details[0].Unpack(info)
```

- 새 에러: `CustomError` 상속 후 `code`, `error_code`, `message` 정의
- `error_code` 형식: `도메인__이유`

## 위급 판정

`EmergencyAnalyzer`가 울음마다 대표 음높이를 구하고, 음역대 안 울음이 연속 몇 번 이어졌는지로 판정한다.

| 기준 | 기본값 |
| --- | --- |
| 음역대 | 4,600~8,000 Hz |
| 위급 판정 | 음역대 안 울음 7회 이상 |
| 대표 음높이 | 울음 구간 전체 파워 스펙트럼의 최대 주파수 |
| 음높이 탐색 범위 | 250~8,000 Hz |
| 판정 단위 | 캡처 1개 |

- 음역대 밖 울음: 횟수에서 제외하고 연속은 끊지 않음
- 울음 검출: `OnsetAnalyzer`가 담당. −39 dBFS 이상, 무음 0.1초 이상이면 분리, 최소 30 ms
- 기본값 근거: 0912 정상 가정 자료에서 앵무로 판정된 6,408개 중 이 기준을 넘는 파일 3개, 0.05%
- 서버 연결: `OnsetServicer`가 앵무 소리로 판정된 캡처만 분석

## proto

| 항목 | 값 |
| --- | --- |
| 인터페이스 정의 원본 | `proto/buddybird/ai/v1/onset.proto` |
| 생성 코드 | `buddybird/ai/v1/`, git에 커밋 |
| 생성 명령 | `make proto` |
| 생성 코드 요구 버전 | grpcio 1.84.0 이상, protobuf 7.35.1 이상 |

- 생성 코드 검사: Ruff 검사 제외, mypy는 함께 생성한 `.pyi` 사용
- CI: `lint` 작업에서 `make proto` 실행 후 `buddybird/` 변경이 있으면 실패
- 필드 규칙: 필드 추가만 허용, 기존 필드 번호의 삭제와 변경 금지

proto를 수정하면 `make proto`로 생성 코드를 갱신하고 함께 커밋한다.

### OnsetService

`AnalyzeSession`은 세션 하나에 여는 양방향 스트림이다.

| 요청 메시지 | 필드 | 값 |
| --- | --- | --- |
| `SessionStart` | `session_id` | `audio_captures.client_session_id` |
| `CaptureInput` | `capture_id` | `audio_captures.client_capture_id` |
| `CaptureInput` | `s3_key` | 데이터 버킷의 `audio_capture/` 객체 key |
| `CaptureInput` | `captured_at` | `audio_captures.captured_at` |

- 첫 메시지: `start`
- 이후 메시지: `captured_at` 순서의 `capture`
- 응답: 캡처마다 `chirp_count`, `window_chirp_count`, `is_emergency` 1개
- 시간 창 상태: 스트림이 열려 있는 동안만 유지, 스트림이 끊기면 초기화
- 서버 등록: 미구현, 호출 시 gRPC 기본 응답 `UNIMPLEMENTED`

### buddybird-api 공유

1. ai-api에서 proto를 수정하고 `make proto` 결과와 함께 PR을 merge한다.
2. `dev` merge 커밋에 `proto-v<버전>` 태그를 생성한다.
3. buddybird-api에 proto 파일을 복사하고 파일 첫 줄 주석에 기준 태그를 작성한다.
4. buddybird-api에서 코드를 생성해 커밋한다.

## 앵무 소리 판정 모델

| 모델 | HuggingFace 저장소 | 버전 | 파일 |
| --- | --- | --- | --- |
| 판정 | `buddybird-ai/parrot-sound-gate` | `v2.0.0` | `gate-2.0.0.joblib` |
| 임베딩 | `justinchuby/Perch-onnx` | 커밋 `da88bf8` | `perch_v2.onnx`, 409 MB |

- 로컬 실행: 첫 시작 때 HuggingFace 캐시로 받고, 이후 캐시 사용
- 컨테이너: 이미지 빌드 때 받아 넣음. 실행 중 다운로드 없음
- 모델 교체: `app/onset/infra/parrot_gate.py`의 버전 상수 수정 후 이미지 재빌드

## 컨테이너

- 실행 명령: `python -m app.main`
- 노출 포트: 50051
- 이미지 아키텍처: ARM64, `deploy` 워크플로에서 빌드
- 판정 모델: 빌드 때 `python -m app.onset.infra.parrot_gate`로 받아 `HF_HOME=/app/models`에 저장
- 실행 중 HuggingFace 접속: 없음, `HF_HUB_OFFLINE=1`

## 검사

| 명령 | 실행 내용 |
| --- | --- |
| `make check` | `ruff check --fix`, `ruff format --check`, `mypy` |
| `make test` | `pytest` |

- `make check`: 자동 수정 가능한 Ruff 위반을 파일에 바로 반영
- Ruff 규칙: `pyproject.toml`의 `[tool.ruff.lint]`
- mypy 설정: `pyproject.toml`의 `[tool.mypy]`
  - strict 모드
  - 검사 대상: `app`, `core`, `tests`
  - 타입 스텁이 없는 `google.rpc`, `grpc_health`, `grpc_status`: import 검사 제외
- pytest 설정: `pytest.ini`
  - `DeprecationWarning` 숨김
- GitHub Actions: `dev`와 `main` 대상 PR에서 `lint`, `test` 실행
  - `lint` 작업: `ruff check`, `ruff format --check`, `mypy`, proto 생성 코드 검사
  - 작업 실패 시 Slack 알림
  - 필요한 저장소 secret: `SLACK_WEBHOOK_URL`
- 로컬 확인 환경: Python 3.12.13, uv 0.12.3
- 로컬 확인 결과
  - Ruff 통과, mypy 통과, 테스트 45개 통과
  - `make local` 실행 후 `make health` 결과 `SERVING`
  - `SIGTERM` 수신 후 서버 종료

## 브랜치

| 브랜치 | 역할 |
| --- | --- |
| `main` | 릴리스 기준 |
| `dev` | 기본 브랜치, 개발 통합 |
| 작업 브랜치 | 티켓별 변경 |

1. `dev`에서 티켓별 작업 브랜치를 생성한다.
2. 사용자 코드 검수 후 작업 브랜치를 GitHub에 push하고 `dev` 대상 PR을 생성한다.
3. CI 결과와 리뷰를 확인하고 PR을 merge한다.
4. 릴리스는 `dev`에서 `main`으로 PR을 생성한다.

저장소 공개 범위는 Private이다. 현재 요금제에서는 자동 브랜치 보호를 적용하지 못하므로 PR과 CI 확인 절차로 관리한다.

## 관련 작업

- [BB-458](https://daheehyeok.atlassian.net/browse/BB-458)
- [BB-493](https://daheehyeok.atlassian.net/browse/BB-493)
- [BB-494](https://daheehyeok.atlassian.net/browse/BB-494)
- [BB-495](https://daheehyeok.atlassian.net/browse/BB-495)
- [BB-498](https://daheehyeok.atlassian.net/browse/BB-498)
