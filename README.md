# buddybird-ai-api

Python 3.12 기반 앵무 울음 분석 프로젝트다. gRPC 서버와 캡처 단위의 울음·음역대 분석 로직을 포함한다.
서버는 gRPC 표준 헬스체크 `grpc.health.v1.Health`와 분석 RPC `OnsetService.AnalyzeSession`을 제공한다.
SQS 요청 큐를 설정하면 사이클 분석 워커도 같은 프로세스에서 실행하며, gRPC와 판정 모델·분석 로직을 공유한다.

## 코드 구조

| 경로 | 역할 |
| --- | --- |
| `app/main.py` | 모델 로딩, gRPC 서버·SQS 워커 실행과 종료 처리 |
| `app/onset/application/` | 사이클 분석, gRPC 서비스, SQS 워커 |
| `app/onset/infra/` | 앵무 소리 판정 모델, S3 오디오 로더, SQS 클라이언트 |
| `app/onset/domain/entities.py` | 울음·분석 결과와 `OnsetCriteria` |
| `app/onset/domain/services.py` | `OnsetAnalyzer`: 울음 검출 |
| `app/onset/domain/emergency.py` | `EmergencyAnalyzer`, `EmergencyCriteria`: 울음별 음역대 판정 |
| `app/onset/domain/loudness.py` | `maxwin_db`, `is_too_quiet`: 앵무 소리 판정 전 음량 게이트 |
| `app/onset/domain/exceptions.py` | 분석 입력·설정 오류 |
| `core/grpc/` | 포트 설정, 헬스체크 CLI, 오류 인터셉터 |
| `proto/buddybird/ai/v1/onset.proto` | 분석 RPC 계약 |
| `buddybird/ai/v1/` | proto에서 생성한 Python 코드와 타입 스텁 |
| `tests/` | 분석 로직, RPC 계약, 서버 테스트 |

## 준비

- 준비 환경: Python 3.12, uv, make
- 명령 실행 위치: 저장소 최상위 디렉터리

의존성을 설치하고 커밋 전 검사 훅을 등록한다.

```sh
make setup
```

`make setup`은 `uv sync`를 실행하고 git `core.hooksPath`를 `.githooks`로 지정한다.
등록한 훅은 커밋할 Python 파일에 `ruff check --fix`와 `ruff format --check`를 실행한다.
포맷 오류가 있으면 `uv run ruff format <파일>`로 수정한 뒤 다시 커밋한다.
CI와 같은 잠금 버전으로 설치하려면 `uv sync --locked`를 사용한다.

## 실행

개발 서버를 실행한다. 포트 기본값은 50051이다. 모델 다운로드·로딩이 완료된 뒤 포트를 열고 `SERVING` 상태가 된다.
캡처 분석에는 `AUDIO_S3_BUCKET`과 해당 객체를 읽을 수 있는 AWS 인증이 필요하다.

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
| 바인딩 주소 | `0.0.0.0`, TLS 없는 gRPC |
| 로그 수준 환경 변수 | `LOG_LEVEL`, 기본값 `INFO` |

- 헬스체크 검사 범위: 서버 응답만 확인, 분석 준비 상태와 외부 서비스 연결 상태는 미검사
- 서버 종료: `Ctrl+C`
  - `SIGINT`, `SIGTERM` 수신 시 헬스체크 상태 `NOT_SERVING`으로 변경
  - gRPC 요청은 최대 10초, SQS 워커는 최대 25초를 병렬로 기다린 뒤 종료

### 헬스체크 명령

로컬 가상환경에서는 다음 명령을 사용한다. 컨테이너 내부에서는 `uv run`을 생략한다.
Dockerfile에 `HEALTHCHECK`는 없으므로 자동 검사는 실행 환경에서 별도로 설정한다.

```sh
uv run python -m core.grpc.healthcheck --target 127.0.0.1:50051
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

## 울음 분석과 위급 판정

`CycleAnalyzer`는 캡처마다 다음 순서로 분석한다. gRPC와 SQS 워커가 같은 순서를 쓴다.

```
S3 다운로드 → 음량 게이트 → 앵무 소리 판정(parrot-sound-gate) → 울음 검출 → 울음별 음역대 판정
```

- 음량 게이트에서 걸리면 이후 단계를 건너뛰고 앵무가 아닌 캡처로 처리한다.
- 울음 검출과 음역대 판정은 앵무 소리로 판정된 캡처에만 한다.

| 용어 | 뜻 | 응답 필드 |
| --- | --- | --- |
| 울음(call) | 울음 검출이 찾은 소리 구간 하나, 음역대 무관 | `call_count` |
| 짹(chirp) | 울음 중 대표 음높이가 위급 음역대 안인 것 | `chirp_count` |

짹은 울음의 일부이므로 `chirp_count`는 항상 `call_count` 이하다.

### 음량 게이트

`maxwin_db`는 100 ms 창을 100 ms 간격으로 옮기며 구한 RMS의 최댓값을 dBFS로 돌려준다.
긴 무음 속 짧은 울음이 평균에 희석되지 않도록 전체 RMS 대신 최대 창을 쓴다. 창보다 짧은 캡처는 전체를 한 창으로 본다.

| 기준 | 값 |
| --- | --- |
| 창 길이·간격 | 100 ms |
| too_quiet | `maxwin_db` < −39 dBFS, −39.0은 통과 |

- 기준 출처: parrot-mimicry `docs/step1-loudness-gate/spec-step1-loudness-gate.md`, 계산은 `scripts/step2/classify_folder.py`의 `maxwin_db()`와 같다.
- too_quiet 캡처 결과: `is_parrot=false`, `score=0.0`, `call_count=0`, `chirp_count=0`. 결과 형식에 별도 필드는 없고, 캡처마다 `capture <id> maxwin_db=<값> too_quiet=<판정>`을 INFO 로그로 남긴다.

두 도메인 분석기(울음 검출, 울음별 음역대 판정)는 캡처 하나를 대상으로 한다.

### 울음 검출

`OnsetAnalyzer`는 full scale을 1로 정규화한 1차원 mono 샘플과 양수인 샘플레이트를 받는다.
오디오 파일 디코딩이나 리샘플링은 수행하지 않는다. 빈 신호와 무음은 울음이 없는 결과를 반환하고,
다차원 입력·NaN·무한대·0 이하 샘플레이트는 `InvalidAudioSignalError`로 거부한다.

| `OnsetCriteria` 기준 | 기본값 |
| --- | --- |
| 분석 프레임 | 10 ms |
| 활성 프레임 | RMS −39 dBFS 이상 |
| 한 울음으로 연결할 무음 | 100 ms 이하, 초과하면 분리 |
| 울음 최소 길이 | 활성 프레임 합계 30 ms 이상, 무음 제외 |

### 울음별 음역대 판정

`EmergencyAnalyzer`는 검출된 울음마다 대표 음높이를 구하고 음역대 안인지 판정한다.
`EmergencyJudgement.in_band_chirps`가 캡처의 음역대 안 울음, 즉 짹이다.

| 기준 | 기본값 |
| --- | --- |
| 음역대 | 4,600~8,000 Hz |
| 위급 기준 (`min_consecutive_chirps`) | 시간 창 안 음역대 안 울음 7회 이상 |
| 대표 음높이 | 울음 구간 전체 파워 스펙트럼의 최대 주파수 |
| 음높이 탐색 범위 | 250~8,000 Hz |

- 음역대 양 끝값 포함. 음역대 밖 울음은 횟수에서 제외한다.
- 판정 기준 변경: `OnsetCriteria` 또는 `EmergencyCriteria`를 생성해 각 분석기의 `criteria` 인자로 전달한다.

### gRPC·SQS 응답의 위급 판정

`CycleAnalyzer`는 각 캡처의 음역대 안 울음 수를 `chirp_count`로 사용한다.
`captured_at` 순서로 처리한 캡처 중 현재 캡처의 `captured_at`부터 30초 전까지의 횟수를 합산하고(30초 경계 포함),
`window_chirp_count >= 7`이면 응답의 `is_emergency`가 true다.
시간 창은 분석 호출마다 초기화되며, gRPC 스트림 간 또는 SQS 사이클 간에 누적되지 않는다.

위급 판정과 별개로, 앵무 소리로 판정된 캡처는 음역대와 관계없이 onset이 검출한 울음 전체 수를 `call_count`로 응답한다.
앵무가 아니거나 음량이 부족하거나 분석에 실패한 캡처의 `call_count`는 0이다.

저장소 루트에서 다음 예제로 도메인 분석기 두 결과를 확인할 수 있다.

```sh
uv run python - <<'PYTHON'
import numpy as np

from app.onset.domain.emergency import EmergencyAnalyzer
from app.onset.domain.services import OnsetAnalyzer

sample_rate = 16000
times = np.arange(round(0.12 * sample_rate)) / sample_rate
chirp = 0.5 * np.sin(2 * np.pi * 5000 * times)
silence = np.zeros(round(0.15 * sample_rate))
samples = np.tile(np.concatenate([chirp, silence]), 7)

analysis = OnsetAnalyzer().analyze(samples=samples, sample_rate=sample_rate)
judgement = EmergencyAnalyzer().judge(analysis=analysis, samples=samples)
print(len(analysis.calls), len(judgement.in_band_chirps))  # 7 7
PYTHON
```

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

`AnalyzeSession`은 세션 하나에 여는 양방향 스트림이다. 서버는 요청 스트림 수신을 완료한 뒤 캡처를 분석하고 응답한다.

| 요청 메시지 | 필드 | 값 |
| --- | --- | --- |
| `SessionStart` | `session_id` | `audio_captures.client_session_id` |
| `CaptureInput` | `capture_id` | `audio_captures.client_capture_id` |
| `CaptureInput` | `s3_key` | 데이터 버킷의 세션 소리 객체 key `user/<user_id>/session/<session_id>/sound/<file_id>` |
| `CaptureInput` | `captured_at` | `audio_captures.captured_at` |

- 첫 메시지: `start`
- 이후 메시지: `captured_at` 순서의 `capture`. 순서가 달라도 서버가 `captured_at`으로 정렬
- 응답: 캡처마다 `capture_id`, `call_count`, `chirp_count`, `window_chirp_count`, `is_emergency`를 포함한 메시지 1개
- 응답 시점: 클라이언트가 전송을 끝낸 뒤 `captured_at` 순서로 한꺼번에 전송
- 캡처 분석: 최대 4개씩 동시에 처리, 실패한 캡처는 `call_count`와 `chirp_count` 0
- 시간 창: 30초, 스트림이 열려 있는 동안만 유지, 스트림이 끊기면 초기화
- 서버 등록: `app/main.py`에서 `OnsetServicer` 등록

### buddybird-api 공유

1. ai-api에서 proto를 수정하고 `make proto` 결과와 함께 PR을 merge한다.
2. `dev` merge 커밋에 `proto-v<버전>` 태그를 생성한다.
3. buddybird-api에 proto 파일을 복사하고 파일 첫 줄 주석에 기준 태그를 작성한다.
4. buddybird-api에서 코드를 생성해 커밋한다.

## SQS 사이클 분석

buddybird-api가 세션 사이클 하나를 요청 큐에 넣으면, 워커가 분석해 결과 큐로 발행한다.
gRPC 서버와 같은 프로세스에서 실행하며 판정 모델을 함께 사용한다.

| 환경 변수 | 값 |
| --- | --- |
| `SQS_PARROT_SOUND_DETECTION_QUEUE_URL` | 요청 큐 URL. 없으면 워커 미실행 |
| `SQS_JUDGMENT_RESULT_QUEUE_URL` | 결과 큐 URL. 요청 큐 URL이 있으면 필수 |
| `SQS_ENDPOINT_URL` | 로컬 elasticmq 주소. 운영에서는 비움 |
| `AUDIO_S3_BUCKET` | 캡처 오디오 버킷 |

### 요청 메시지

```json
{
  "type": "cycle.analyze",
  "session_id": "0199…",
  "cycle": 3,
  "sounds": [
    {"sound_id": "0199…", "object_key": "user/…/session/…/sound/…", "captured_at": "2026-09-23T10:00:00Z"}
  ]
}
```

- `sounds`: 사이클의 캡처 전체, 1개 이상. 순서 무관
- `sound_id`: `session_sounds.id`
- `object_key`: `files.file_path`. 데이터 버킷의 `user/{user_id}/session/{session_id}/sound/{file_id}`
- `captured_at`: ISO 8601, 시간대 필수

### 결과 메시지

```json
{
  "type": "cycle.analyzed",
  "session_id": "0199…",
  "cycle": 3,
  "model_version": "parrot-sound-gate@v2.0.0",
  "analyzed_at": "2026-09-23T10:05:12.345678+00:00",
  "is_emergency": false,
  "call_count": 11,
  "sounds": [
    {"sound_id": "0199…", "is_parrot": true, "score": 0.93,
     "call_count": 11, "chirp_count": 4, "window_chirp_count": 6, "is_emergency": false}
  ]
}
```

- `sounds`: `captured_at` 순서
- `score`: 앵무 소리 판정 확률. `is_parrot`이 false면 `call_count`와 `chirp_count` 0
- `call_count`: 캡처의 울음 전체 수, 음역대 무관. 최상위 값은 사이클 안 캡처의 합
- `window_chirp_count`: 직전 30초 안 같은 사이클 캡처의 chirp 합. 사이클 사이에는 이어지지 않음
- `is_emergency`: 캡처별로 `window_chirp_count` 7 이상. 최상위 값은 캡처 중 하나라도 true

### 처리 규칙

| 상황 | 동작 |
| --- | --- |
| 분석 성공 | 결과 발행 후 요청 삭제 |
| 캡처 하나라도 실패 | 결과 미발행, 요청 유지. 재수신 횟수와 DLQ 이동은 요청 큐의 redrive policy에 따름 |
| 형식이 잘못된 요청 | 요청 유지. 재수신 횟수와 DLQ 이동은 요청 큐의 redrive policy에 따름. 빈 값, `null`, 타입이 다른 필드, 시간대 없는 `captured_at` 포함 |
| 분석이 길어짐 | 60초마다 요청 가시성을 300초로 연장 |
| 서버 종료(`SIGTERM`) | 새 수신 중단, 처리 중인 사이클은 최대 25초 대기. 넘기면 요청을 즉시 큐에 반환 |

- 중복 결과: 결과 발행 뒤 요청 삭제 전에 종료되면 같은 결과를 다시 발행. buddybird-api에서 `session_id`, `cycle`, `model_version`으로 중복 제거
- 처리 시간: 사이클마다 `사이클 분석 완료 … elapsed=` 로그

### 로컬 실행

#### dev 큐에 연결

실제 dev SQS와 데이터 버킷을 사용한다. Docker가 필요 없고 dev 버킷 읽기 권한이 있는 AWS 인증(`aws sso login`)이 필요하다.

1. `.env.example`을 `.env.dev`로 복사하고 dev 리전, 버킷, 두 큐 URL을 채운다. 값은 aws-infra 출력이나 AWS 콘솔에서 확인한다.
2. 서버를 실행한다.

```sh
make local ENV_FILE=.env.dev port=50061
```

다른 터미널에서 요청을 보내고 결과를 확인한다. `object_key`는 dev 버킷에 있는 오디오 key를 사용한다.

```sh
set -a; . ./.env.dev; set +a
aws sqs send-message --queue-url "$SQS_PARROT_SOUND_DETECTION_QUEUE_URL" \
  --message-body '{"type":"cycle.analyze","session_id":"local-test","cycle":1,"sounds":[{"sound_id":"s1","object_key":"<key>","captured_at":"2026-09-27T10:00:00Z"}]}'
aws sqs receive-message --queue-url "$SQS_JUDGMENT_RESULT_QUEUE_URL" --wait-time-seconds 10
```

- 사전 확인: 두 큐의 메시지 수가 0인지 확인. dev ai-api 서비스가 실행 중이면 요청을 나눠 가져가므로 사용하지 않음
- 정리: 받은 결과는 `aws sqs delete-message`로 삭제. buddybird-api dev consumer가 결과 큐를 소비하기 시작하면 결과 확인은 consumer 로그로 대체
- 확인 기록(2026-09-27): 소리 3개 사이클 2.8초, 결과 1건 발행과 요청 삭제, `SIGTERM` 후 14초에 정상 종료

#### elasticmq

큐를 로컬에서 흉내 낸다. 아직 이 절차로 실행해 본 적은 없다.

```sh
docker run --rm -p 9324:9324 softwaremill/elasticmq-native
aws --endpoint-url http://localhost:9324 --region ap-northeast-2 sqs create-queue --queue-name request
aws --endpoint-url http://localhost:9324 --region ap-northeast-2 sqs create-queue --queue-name result

AWS_DEFAULT_REGION=ap-northeast-2 \
SQS_ENDPOINT_URL=http://localhost:9324 \
SQS_PARROT_SOUND_DETECTION_QUEUE_URL=http://localhost:9324/000000000000/request \
SQS_JUDGMENT_RESULT_QUEUE_URL=http://localhost:9324/000000000000/result \
AUDIO_S3_BUCKET='실제-dev-데이터-버킷명' \
make local
```

- elasticmq 인증: 임의 값 허용. S3 읽기에는 dev 버킷 권한이 있는 AWS 인증 필요

## 앵무 소리 판정 모델

| 모델 | HuggingFace 저장소 | 버전 | 파일 |
| --- | --- | --- | --- |
| 판정 | `buddybird-ai/parrot-sound-gate` | `v2.0.0` | `gate-2.0.0.joblib` |
| 임베딩 | `justinchuby/Perch-onnx` | 커밋 `da88bf8` | `perch_v2.onnx`, 409 MB |

- 로컬 실행: 첫 시작 때 HuggingFace 캐시로 받고, 이후 캐시 사용
- 컨테이너: 이미지 빌드 때 받아 넣음. 실행 중 다운로드 없음
- HuggingFace 업로드 절차: parrot-mimicry `docs/ops/huggingface.md`

### 모델 버전 올리기

HuggingFace에 새 태그가 올라와도 자동 반영하지 않는다. 버전 고정 후 PR로 교체한다.

1. `app/onset/infra/parrot_gate.py`의 상수 수정
   - `_GATE_REVISION`: 새 태그
   - `_GATE_FILE`: 새 태그의 파일명
   - `_PERCH_REVISION`: 새 태그 `model_manifest.json`의 Perch 커밋
2. `make local`로 모델 다운로드와 서버 시작 확인
3. `make check`, `make test` 통과 확인
4. 이 README의 모델 표 갱신 후 PR 생성, `dev` merge
5. GitHub Actions `deploy` 워크플로 수동 실행. 이미지 빌드 때 새 모델이 포함됨

## 컨테이너

- 실행 명령: `python -m app.main`
- 노출 포트: 50051
- 의존성: `uv sync --locked --no-dev --no-install-project`로 설치
- 이미지 아키텍처: 배포 워크플로에서 `linux/arm64`로 빌드
- 판정 모델: 빌드 때 `python -m app.onset.infra.parrot_gate`로 받아 `HF_HOME=/app/models`에 저장
- 실행 중 HuggingFace 접속: 없음, `HF_HUB_OFFLINE=1`

로컬 이미지 실행과 헬스체크:

```sh
docker build -t buddybird-ai-api:local .
docker run --rm -p 50051:50051 --name buddybird-ai-api buddybird-ai-api:local
# 별도 터미널에서 실행
docker exec buddybird-ai-api python -m core.grpc.healthcheck
```

### ECR 이미지 배포

[deploy 워크플로](.github/workflows/deploy.yml)는 `workflow_dispatch`로 수동 실행한다.

| 설정 | 값 |
| --- | --- |
| 실행 환경 | `ubuntu-24.04-arm` |
| AWS 리전 | 저장소 variable `AWS_REGION` |
| ECR 저장소 | 저장소 variable `ECR_REPOSITORY` |
| 인증 | OIDC, 저장소 secret `AWS_ROLE_ARN` |
| 이미지 태그 | 입력 `image_tag`, 비우면 실행 커밋 SHA |

워크플로는 이미지를 빌드하고 ECR에 push하는 단계까지 수행한다.
실행 중인 서비스의 이미지 교체나 재시작 단계는 포함되어 있지 않다.

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
- GitHub Actions: `dev`와 `main` 대상 PR 또는 수동 실행 시 `lint`, `test` 실행
  - `lint` 작업: `ruff check`, `ruff format --check`, `mypy`, proto 생성 코드 검사
  - 작업 실패 시 Slack 알림
  - 필요한 저장소 secret: `SLACK_WEBHOOK_URL`

검증 결과는 실행 시점의 코드와 환경에 따라 달라진다. 로컬에서 CI와 같은 검사를 수행하려면:

```sh
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
make test
make proto
git status --short -- buddybird
```

마지막 명령에 출력이 없어야 생성 코드가 proto와 일치한다.
특정 테스트만 실행하려면 `make test ARGS="tests/test_emergency.py -q"`를 사용한다.

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

PR을 merge하기 전에 CI 결과와 리뷰를 확인한다.

## 관련 작업

- BB-458
- BB-493
- BB-494
- BB-495
- BB-498
- BB-509
- BB-538
- BB-544
- BB-552
