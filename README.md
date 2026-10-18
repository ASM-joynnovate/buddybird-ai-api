# buddybird-audio-ai

buddybird-api가 SQS 요청 큐에 넣은 소리를 판정하는 Lambda 함수 두 개의 저장소다.
앵무새 소리 판별 함수는 소리가 앵무새 소리인지 판별하고 울음 수를 센다.
모사 판정 함수는 앵무새 소리가 세션의 학습 단어를 따라 했는지 판정한다.
두 함수는 이미지를 따로 사용하고, 결과를 같은 결과 큐로 발행한다.
HTTP나 gRPC로 요청을 받지 않는다.

| 함수 | Lambda 함수 | 요청 큐 | 요청 type | 결과 type |
| --- | --- | --- | --- | --- |
| 앵무새 소리 판별 | `jn-buddybird-parrot-detection-<env>` | `parrot-sound-detection` | `audio.detect_parrot` | `audio.parrot_detected` |
| 모사 판정 | `jn-buddybird-mimic-judgment-<env>` | `mimicry-judgment` | `audio.judge_mimic` | `audio.mimic_judged` |

## 코드 구조

| 경로 | 역할 |
| --- | --- |
| `app/config.py` | 공통 환경 변수와 `pyproject.toml`의 이름, 버전 읽기 |
| `app/sentry.py` | Sentry 초기화 |
| `app/sqs.py` | SQS 배치 처리. 메시지마다 Sentry trace를 이어 받아 결과를 발행하고, 실패한 메시지를 `batchItemFailures`로 반환 |
| `app/parrot_detection/handler.py` | 앵무새 소리 판별 Lambda handler. 모델을 올리고 결과 메시지를 생성 |
| `app/parrot_detection/detection.py` | 소리 하나를 S3에서 읽어 음량 게이트, 앵무새 소리 판별, 울음 수 계산 |
| `app/parrot_detection/model.py` | 앵무새 소리 판별 모델 |
| `app/parrot_detection/loudness.py` | `maxwin_db`, `is_too_quiet`: 음량 게이트 |
| `app/parrot_detection/calls.py` | `detect_calls`, `count_chirps`: 울음 검출과 짹 수 계산 |
| `app/parrot_detection/config.py` | 앵무새 소리 판별 이미지의 환경 변수 읽기 |
| `app/mimic_judgment/handler.py` | 모사 판정 Lambda handler. 모델을 올리고 결과 메시지를 생성 |
| `app/mimic_judgment/judgment.py` | 모사 판정 모델 로드. 판정할 소리와 기준음성을 S3에서 받아 판정 |
| `app/mimic_judgment/config.py` | 모사 판정 이미지의 환경 변수 읽기 |
| `scripts/download_parrot_detection_model.py` | 이미지를 빌드할 때 앵무새 소리 판별 모델을 받는 스크립트 |
| `scripts/download_mimic_judgment_model.py` | 이미지를 빌드할 때 모사 판정 모델을 받고 해시를 확인하는 스크립트 |
| `tests/parrot_detection/` | 앵무새 소리 판별 handler, 소리 분석, 울음 검출, 음량 게이트 테스트 |
| `tests/mimic_judgment/` | 모사 판정 handler, S3 다운로드 테스트 |
| `tests/ci/` | Slack 알림 길이 제한 테스트 |

## 준비

- 준비 환경: Python 3.12, uv, make, Docker
- 명령 실행 위치: 저장소 최상위 디렉터리

의존성을 설치하고 커밋 전 검사 훅을 등록한다.

```sh
make setup
```

`make setup`은 `uv sync`를 실행하고 git `core.hooksPath`를 `.githooks`로 지정한다.
`uv sync`는 `dev` 그룹과 `parrot-detection` 그룹을 설치한다.
모사 판정 의존성인 `mimic-judgment` 그룹은 이미지에만 설치하고, 테스트는 모사 판정 모델을 fake로 바꿔 실행한다.
등록한 훅은 커밋할 Python 파일에 `ruff check --fix`와 `ruff format --check`를 실행한다.
포맷 오류가 있으면 `uv run ruff format <파일>`로 수정한 뒤 다시 커밋한다.
CI와 같은 잠금 버전으로 설치하려면 `uv sync --frozen`을 사용한다.

## 실행

Lambda 이미지를 빌드하고 Runtime Interface Emulator(RIE)로 실행한다.
RIE는 base 이미지에 들어 있는 로컬 Lambda 실행 서버다.
두 판정 모두 `S3_BUCKET`과 그 버킷을 읽을 수 있는 AWS 임시 자격 증명이 필요하다.

1. `.env.example`을 `.env.dev`로 복사하고 리전, 버킷, 결과 큐 URL을 채운다.
2. 임시 자격 증명을 셸 환경 변수로 내보낸 뒤, 실행할 함수를 `FUNCTION`으로 고른다. 기본값은 `parrot-detection`이다.

```sh
eval "$(aws configure export-credentials --profile <프로필> --format env)"
make local FUNCTION=parrot-detection ENV_FILE=.env.dev
```

3. 다른 터미널에서 SQS 이벤트를 보낸다. 응답에는 처리에 실패한 메시지가 들어 있다.

```sh
curl -XPOST "http://localhost:8080/2015-03-31/functions/function/invocations" -d '{
  "Records": [
    {"messageId": "m-1", "body": "{\"type\": \"audio.detect_parrot\", \"session_id\": \"s-1\", \"data\": [{\"audio_id\": \"a-1\", \"object_key\": \"<키>\", \"captured_at\": \"2026-10-06T10:00:00+00:00\"}]}"}
  ]
}'
# {"batchItemFailures": []}
```

모사 판정은 `make local FUNCTION=mimic-judgment ENV_FILE=.env.dev`로 실행하고 다음 이벤트를 보낸다.

```sh
curl -XPOST "http://localhost:8080/2015-03-31/functions/function/invocations" -d '{
  "Records": [
    {"messageId": "m-1", "body": "{\"type\": \"audio.judge_mimic\", \"session_id\": \"s-1\", \"target\": {\"audio_id\": \"a-1\", \"object_key\": \"<키>\"}, \"reference\": {\"word_id\": \"w-1\", \"word_name\": \"안녕\", \"object_keys\": [\"<기준음성 키>\"]}}"}
  ]
}'
# {"batchItemFailures": []}
```

- 환경 변수는 [공통 환경 변수](#공통-환경-변수) 표를 따른다.
- `make local`은 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`을 컨테이너에 그대로 넘기고 `~/.aws`를 마운트하지 않는다. SSO 프로필은 토큰을 갱신하면서 `~/.aws/sso/cache`에 파일을 저장하므로, 읽기 전용으로 마운트하면 S3 읽기가 모두 실패한다.
- 결과는 로컬 elasticmq로 보낸다. 실제 dev 결과 큐로 보내면 dev consumer가 그 결과를 dev DB에 저장한다.
- 종료: `Ctrl+C`

elasticmq를 실행하고 결과 큐를 만든다.
buddybird-api compose의 elasticmq가 이미 9324 포트에서 실행 중이면 그 `judgment-result` 큐를 사용하고, 이때 결과는 로컬 api consumer가 읽는다.

```sh
docker run --rm -p 9324:9324 softwaremill/elasticmq-native
aws --endpoint-url http://localhost:9324 --region ap-northeast-2 sqs create-queue --queue-name judgment-result
```

컨테이너 안에서는 호스트를 `host.docker.internal`로 부르므로 `.env.dev`에 다음처럼 적는다.

```sh
SQS_ENDPOINT_URL=http://host.docker.internal:9324
SQS_JUDGMENT_RESULT_QUEUE_URL=http://host.docker.internal:9324/000000000000/judgment-result
```

## SQS 처리

buddybird-api가 요청 큐에 메시지를 넣으면, SQS 트리거가 메시지를 묶어 Lambda를 호출한다.
Lambda는 메시지마다 결과 메시지 하나를 결과 큐로 발행한다.

### 공통 환경 변수

두 함수는 같은 환경 변수를 읽는다.

| 환경 변수 | 값 |
| --- | --- |
| `SQS_JUDGMENT_RESULT_QUEUE_URL` | 결과 큐 URL. 필수. 없으면 초기화 단계에서 실패 |
| `S3_BUCKET` | 소리와 기준음성 버킷. 필수. 없으면 초기화 단계에서 실패 |
| `SQS_ENDPOINT_URL` | 로컬 elasticmq 주소. 운영에서는 비움 |
| `ENV` | Sentry environment. 비우면 `local` |
| `SENTRY_DSN` | buddybird-audio-ai Sentry 프로젝트 DSN. 비우면 Sentry로 보내지 않음 |
| `LOG_LEVEL` | 로그 수준. 기본값 `INFO` |

### 공통 처리 규칙

| 상황 | 동작 |
| --- | --- |
| 판정 성공 | 결과 발행. 요청 삭제는 SQS 트리거가 함 |
| 요청을 읽지 못하거나 판정 또는 결과 발행 실패 | 결과 미발행. 그 메시지만 `batchItemFailures`로 돌려주고 같은 배치의 다른 메시지는 영향 없음 |
| 실패한 메시지 | 요청 큐의 visibility timeout 뒤 다시 처리. 5번 실패하면 SQS가 DLQ로 옮기고, buddybird-api consumer가 그 소리를 판정 실패로 기록 |
| 제한 시간 초과나 처리하지 못한 예외 | 응답이 없어 배치 전체를 다시 처리. 이미 발행한 결과도 다시 발행 |

- 처리에 실패하면 `앵무새 소리 판별 요청 처리 실패; message_id=<id>`나 `모사 판정 요청 처리 실패; message_id=<id>`를 ERROR 로그로 남긴다.
- Lambda는 buddybird-api가 보낸 값을 검증하지 않고 그대로 읽는다. 필드가 없거나 읽을 수 없으면 그 메시지는 처리 실패다.
- 메시지 속성의 Sentry trace header(`sentry-trace`, `baggage`)를 이어 받고, 결과 메시지에도 같은 trace header를 붙인다.

## 앵무새 소리 판별

`detection.detect`는 소리마다 다음 순서로 분석한다.

```text
S3 다운로드, 음량 게이트, 앵무새 소리 판별, 울음 검출, 짹 수 계산
```

- 음량 게이트에서 걸리면 이후 단계를 건너뛰고 앵무새 소리가 아닌 것으로 처리한다.
- 울음 검출과 짹 수 계산은 앵무새 소리로 판별된 소리에만 한다.

| 용어 | 뜻 | 결과 필드 |
| --- | --- | --- |
| 울음(call) | 울음 검출이 찾은 소리 구간 하나, 음역대 무관 | `call_count` |
| 짹(chirp) | 울음 중 대표 음높이가 4,600~8,000 Hz인 것 | `chirp_count` |

짹은 울음의 일부이므로 `chirp_count`는 항상 `call_count` 이하다.
앵무새 소리가 아니거나 음량 게이트에서 걸린 소리의 `call_count`와 `chirp_count`는 0이다.
위급 판정은 buddybird-api가 결과를 저장할 때 한다.
소리를 포함한 직전 30초의 `chirp_count` 합계가 7 이상이면 위급 구간이다.

### 음량 게이트

`maxwin_db`는 100 ms window를 100 ms 간격으로 옮기며 구한 RMS의 최댓값을 dBFS로 돌려준다.
긴 무음 속 짧은 울음이 평균에 희석되지 않도록 전체 RMS 대신 가장 큰 window 값을 사용한다.
window보다 짧은 소리는 전체를 window 하나로 본다.

| 기준 | 값 |
| --- | --- |
| window 길이와 간격 | 100 ms |
| `too_quiet` | `maxwin_db` < −39 dBFS, −39.0은 통과. BB-371에서 확정한 값 |

- 기준 출처: parrot-mimicry `docs/step1-loudness-gate/spec-step1-loudness-gate.md`. 계산은 `scripts/step2/classify_folder.py`의 `maxwin_db()`와 같고, `tests/parrot_detection/test_loudness.py`의 `reference_maxwin_db`가 그 계산의 사본이다.
- `too_quiet` 소리의 결과: `is_parrot=false`, `score=0.0`, `call_count=0`, `chirp_count=0`. 소리마다 `음량 측정; audio_id=<id> maxwin_db=<값> too_quiet=<판정>`을 INFO 로그로 남긴다.

### 울음 검출

`detect_calls`는 full scale을 1로 정규화한 1차원 mono 샘플을 받아 울음마다 시작과 끝 샘플 위치를 돌려준다.
기본 기준은 BB-494 조사에서 승인했으며, 울음 사이 무음 허용 시간은 BB-638에서 30 ms로 조정했다.

| 기준 | 값 |
| --- | --- |
| 분석 frame | 10 ms |
| 활성 frame | RMS −39 dBFS 이상 |
| 한 울음으로 연결할 무음 | 30 ms 이하, 초과하면 분리. `call_count`와 `chirp_count`에 동일 적용 |
| 울음 최소 길이 | 활성 frame 합계 30 ms 이상, 무음 제외 |

### 짹 수 계산

`count_chirps`는 울음마다 대표 음높이를 구하고, 대표 음높이가 4,600~8,000 Hz인 울음 수를 센다.
음역대는 0912 자료를 측정해 정한 값이다.

| 기준 | 값 |
| --- | --- |
| 음역대 | 4,600~8,000 Hz, 양 끝 포함 |
| 대표 음높이 | 울음 구간을 1,024 샘플 window, 160 샘플 hop으로 나눈 파워 스펙트럼 합에서 가장 큰 주파수 |
| 음높이 탐색 범위 | 250~8,000 Hz |

저장소 루트에서 다음 예제로 두 함수의 결과를 확인할 수 있다.

```sh
uv run python - <<'PYTHON'
import numpy as np

from app.parrot_detection.calls import count_chirps, detect_calls

sample_rate = 16000
times = np.arange(round(0.12 * sample_rate)) / sample_rate
chirp = 0.5 * np.sin(2 * np.pi * 5000 * times)
silence = np.zeros(round(0.15 * sample_rate))
audio = np.tile(np.concatenate([chirp, silence]), 7)

calls = detect_calls(audio, sample_rate)
print(len(calls), count_chirps(audio, sample_rate, calls))  # 7 7
PYTHON
```

### 앵무새 소리 판별 요청 메시지

```json
{
  "type": "audio.detect_parrot",
  "session_id": "0199…",
  "data": [
    {"audio_id": "0199…", "object_key": "user/…/session/…/sound/…/sound.wav", "captured_at": "2026-10-06T10:00:00+00:00"}
  ]
}
```

- `data`: 소리 하나. 하나가 아니면 처리 실패
- `audio_id`: buddybird-api `session_sounds.id`
- `object_key`: 데이터 버킷의 객체 키. 예: `user/{user_id}/session/{session_id}/sound/{file_id}/sound.wav`
- `captured_at`: 읽지 않음. 위급 판정은 buddybird-api가 함

### 앵무새 소리 판별 결과 메시지

```json
{
  "type": "audio.parrot_detected",
  "session_id": "0199…",
  "model_version": "parrot-sound-gate@v2.0.0",
  "analyzed_at": "2026-10-06T14:45:32.153710+00:00",
  "data": [
    {"audio_id": "0199…", "is_parrot": true, "score": 0.93, "call_count": 11, "chirp_count": 4}
  ]
}
```

- 메시지 하나에 요청과 같은 소리 하나를 담는다
- `model_version`: 이미지를 빌드할 때 정한 앵무새 소리 판별 모델 버전
- `analyzed_at`: 결과를 만든 UTC 시각, ISO 8601, 시간대 포함
- `score`: 앵무새 소리 판별 확률. `is_parrot`이 false면 `call_count`와 `chirp_count`는 0
- `call_count`: 울음 전체 수, 음역대 무관
- `chirp_count`: 짹 수
- 같은 요청을 다시 처리하면 `analyzed_at`만 다른 같은 결과를 발행한다

### 앵무새 소리 판별 Lambda 설정

| 설정 | 값 |
| --- | --- |
| 메모리, 제한 시간 | 4,096 MB, 60초 |
| SQS 트리거 | `parrot-sound-detection` 큐, 배치 10개, `ReportBatchItemFailures`, 최대 동시 실행 10 |
| 요청 큐 | visibility timeout 360초, 5번 실패하면 `parrot-sound-detection-dlq`로 이동 |
| 배치 안 동시 판별 | 최대 4개 |

- Lambda와 SQS 트리거는 aws-infra `buddybird-app`이 만든다.
- 확인 기록(2026-10-06, RIE): 10개 배치는 실패 없이 처리, 없는 키와 JSON이 아닌 본문만 `batchItemFailures`로 반환, 제한 시간 2초에서 30개 중 일부를 발행한 뒤 중단되었고 다시 처리한 결과는 `analyzed_at`만 다름
- 확인 기록(2026-10-18): dev 세션 소리 14개에서 이 이미지와 1.3.0 이미지의 판별 결과가 모두 같음. 앵무새 소리 1개 포함. RIE(2.31 CPU, 읽기 전용 파일 시스템)에서 init 0.7초

### 앵무새 소리 판별 모델

| 모델 | HuggingFace 저장소 | 버전 | 파일 |
| --- | --- | --- | --- |
| 판별 | `buddybird-ai/parrot-sound-gate` | `v2.0.0`, 커밋 `1682b03` | `gate-2.0.0.joblib` |
| 임베딩 | `justinchuby/Perch-onnx` | 커밋 `da88bf8` | `perch_v2.onnx`, 409 MB |

- 이미지를 빌드할 때 판별 모델 커밋의 `model_manifest.json`을 받아, 판별 모델 파일 이름과 Perch 저장소, 파일, 커밋을 읽는다. 판별 모델이 학습에 사용한 Perch만 받도록 Perch 커밋은 따로 정하지 않는다.
- 두 모델을 `/var/task/models`에 넣고, Perch는 `embedding` 출력만 남겨 45 MB로 줄인다.
- 판별 모델 파일은 manifest `model.sha256`, 원본 Perch 파일은 manifest `perch.sha256`과 대조하고, 다르면 빌드가 실패한다.
- 실행 중 HuggingFace 접속: 없음. 이미지에는 huggingface-hub가 없음
- 모델을 올리면 `앵무새 소리 판별 모델 로드 완료; version=<model_version> threshold=<값>`을 INFO 로그로 남긴다.
- scikit-learn은 판별 모델을 저장한 버전인 1.9.0으로 고정한다. 다른 버전이면 모델을 불러올 때 `InconsistentVersionWarning`을 남긴다.
- `onnxruntime`을 import할 때 `blkid`, `hostname` 명령을 찾지 못했다는 줄을 stderr에 남긴다. base 이미지에 두 명령이 없어서 생기며, 190개 소리 비교에서 결과에 영향이 없었다.
- HuggingFace 업로드 절차: parrot-mimicry `docs/ops/huggingface.md`

## 모사 판정

buddybird-api는 `audio.parrot_detected` 결과에서 `is_parrot`이 true인 소리만 `mimicry-judgment` 큐로 모사 판정을 요청한다.
모사 판정 모델은 사람 음성을 거르지 못하므로, 앵무새 소리 판별을 통과하지 않은 소리는 보내지 않는다.

### 모사 판정 요청 메시지

```json
{
  "type": "audio.judge_mimic",
  "session_id": "0199…",
  "target": {"audio_id": "0199…", "object_key": "user/…/session/…/sound/…/sound.wav"},
  "reference": {
    "word_id": "0199…",
    "word_name": "안녕",
    "object_keys": ["user/…/word/…/recording.m4a", "preset/…/recording.m4a"]
  }
}
```

- `target`: 판정할 세션 소리. `audio_id`는 `session_sounds.id`, `object_key`는 데이터 버킷의 객체 키
- `reference`: 비교할 단어와 기준음성
  - `word_id`: 세션의 학습 단어 `words.id`
  - `word_name`: `words.name`. 모델 풀의 단어와 NFC로 정확히 같아야 풀을 사용한다. 풀이 없는 단어는 기준음성만으로 판정한다
  - `object_keys`: 그 단어의 `word_recordings` 전부의 객체 키. 프리셋 녹음을 포함하고 0개도 가능

### 모사 판정 결과 메시지

```json
{
  "type": "audio.mimic_judged",
  "session_id": "0199…",
  "model_version": "parrot-mimicry-judgment@v1.0.0",
  "analyzed_at": "2026-10-16T05:12:03.481920+00:00",
  "target": {"audio_id": "0199…"},
  "reference": {"word_id": "0199…"},
  "judgment": {"status": "ok", "is_success": true, "score": 0.996, "n_own": 2, "n_fill": 18, "set_size": 20}
}
```

- `session_id`, `target.audio_id`, `reference.word_id`: 요청 값을 그대로 돌려준다. buddybird-api는 `session_id`로 세션 리포트를 갱신한다
- `judgment.status`: `ok` 또는 `no_reference`. `no_reference`는 풀과 기준음성이 모두 없을 때다
- `judgment.is_success`: 성공 여부. `score`로 다시 계산하지 않는다
- `judgment.score`: 비발화 앵무새 소리 대비 백분위, 0~1. 실패한 소리도 0.9 이상이 흔하므로 그대로 사용자에게 보여주지 않는다. `status`가 `no_reference`이면 null
- `judgment.n_own`, `judgment.n_fill`, `judgment.set_size`: 비교 세트에 들어간 기준음성 수, 풀에서 채운 녹음 수, 둘의 합
- `model_version`: 이미지를 빌드할 때 정한 모사 판정 모델 버전. buddybird-api가 `mimic_judgments.model_version`에 저장한다
- 판정할 때마다 `모사 판정 결과; audio_id=<id> word_id=<id> status=<값> ... n_own=<값> n_fill=<값> set_size=<값>`을 INFO 로그로 남기고, 같은 값을 Sentry span 속성으로 남긴다

### 모사 판정 Lambda 설정

| 설정 | 값 |
| --- | --- |
| 메모리, 제한 시간 | 4,096 MB, 120초 |
| SQS 트리거 | `mimicry-judgment` 큐, 배치 1개, `ReportBatchItemFailures`, 최대 동시 실행 10 |
| 요청 큐 | visibility timeout 720초, 5번 실패하면 `mimicry-judgment-dlq`로 이동 |
| 배치 안 동시 판정 | 1개 |

- 소리나 기준음성을 읽지 못하거나, 빈 오디오이거나, 디코딩에 실패하면 결과를 발행하지 않고 그 메시지를 `batchItemFailures`로 돌려준다.
- 모델 인스턴스 하나를 여러 스레드가 동시에 사용해도 되는지 검증되지 않았다. 그래서 handler가 메시지를 하나씩 처리하고, SQS 트리거의 배치도 1개다.
- 모델은 init에서 올린다. 1.3.0 dev Lambda에서는 모사 판정 모델 로드에 11~33초가 걸렸다. init이 10초 제한을 넘으면 Lambda는 `INIT_REPORT ... Phase: init Status: timeout`을 남기고 첫 요청 안에서 init을 다시 한다.
- 제한 시간 120초는 dev에서 관측한 cold start 첫 요청 약 80초(모델 로드 33초, 첫 판정 47초)를 기준으로 정했다. 배포한 뒤 CloudWatch Logs Insights로 `REPORT` 줄의 `@initDuration`, `@duration`, `@maxMemoryUsed`를 확인해 조정한다.

### 모사 판정 모델

| 모델 | HuggingFace 저장소 | 버전 | 파일 |
| --- | --- | --- | --- |
| 판정 | `buddybird-ai/parrot-mimicry-judgment` | `v1.0.0`, 커밋 `b1ba789` | `judge/`, `manifest.json`, 특징 파일 3개, 438 MB |
| 인코더 | `lengyue233/content-vec-best` | 커밋 `ab04aa7` | `config.json`, `pytorch_model.bin`, 361 MB |

- 이미지를 빌드할 때 두 저장소를 받아 `/var/task/models/mimic`, `/var/task/models/contentvec`에 넣는다. 인코더 저장소와 커밋은 판정 모델의 `manifest.json`에서 읽는다.
- 번들 파일은 `manifest.json`의 SHA-256, 인코더 가중치는 manifest `encoder.sha256`과 대조하고, 다르면 빌드가 실패한다.
- 실행 중 HuggingFace 접속: 없음. `HF_HUB_OFFLINE=1`이고, 인코더는 로컬 디렉터리에서 읽음
- 판정은 모델 저장소의 `judge` 패키지가 제공하는 `MimicryJudge.judge_audio`로 한다. 의존성은 `pyproject.toml`의 `mimic-judgment` 그룹에 모델 저장소 `uv.lock`과 같은 버전으로 고정
- Linux torch는 CPU 빌드(`download.pytorch.org/whl/cpu`)를 사용한다. PyPI 빌드는 CUDA 패키지를 함께 설치한다
- m4a는 `imageio-ffmpeg`에 들어 있는 ffmpeg로 읽는다. 이미지에서 `/usr/local/bin/ffmpeg`로 연결
- 기준음성 특징과 세트는 캐시하지 않는다. 같은 단어를 반복 판정할 때 `prepare_set` 캐시를 검토한다
- 확인 기록(2026-10-16)
  - macOS arm64: 공개 앵무새 소리 샘플 5건에서 앱 판정 결과와 모델의 `MimicryJudge.judge_audio` 결과가 같음. m4a 기준음성 포함
  - Lambda 이미지(Linux arm64, CPU torch): 같은 5건의 결과가 macOS와 소수점까지 같음. 네트워크 차단, 읽기 전용 파일 시스템에서 실행
- 확인 기록(2026-10-18)
  - dev 세션 소리와 프리셋 m4a 기준음성 2개에서 `MimicryJudge.judge_audio`와 이전 구현의 직접 계산 결과가 같음. 백분위 0.1055, 세트 원점수 −0.8805178850889206
  - RIE(2.31 CPU, 읽기 전용 파일 시스템): init 2.4초, 첫 판정 13.9초, 없는 기준음성 키만 `batchItemFailures`로 반환

## 모델 버전 바꾸기

모델 버전은 Dockerfile 맨 위의 build arg 기본값으로 정한다.
코드에는 모델 버전을 적지 않는다.

| build arg | 대상 | 실행 중 읽는 곳 |
| --- | --- | --- |
| `PARROT_DETECTION_MODEL_REVISION` | 앵무새 소리 판별 모델 커밋, 40자. Perch는 이 커밋의 manifest를 따름 | 없음 |
| `PARROT_DETECTION_MODEL_VERSION` | 앵무새 소리 판별 결과의 `model_version` 값 | 이미지 `ENV`, `app/parrot_detection/config.py` |
| `MIMIC_JUDGMENT_MODEL_REVISION` | 모사 판정 모델 커밋, 40자 | 없음 |
| `MIMIC_JUDGMENT_MODEL_VERSION` | 모사 판정 결과의 `model_version` 값 | 이미지 `ENV`, `app/mimic_judgment/config.py` |

모델 build arg는 그 값을 사용하는 stage에서만 선언한다.
그래서 모델 하나의 버전을 바꾸면 그 모델만 다시 받고, 다른 이미지와 의존성 설치는 cache를 그대로 사용한다.
HuggingFace에 새 버전이 올라와도 자동으로 반영하지 않는다.

`*_MODEL_REVISION`에는 tag가 가리키는 커밋 40자를 넣는다.
HuggingFace tag는 지우고 같은 이름으로 다른 커밋에 다시 만들 수 있고, Docker 빌드 cache는 build arg 문자열이 같으면 모델을 다시 받지 않는다.
tag의 커밋은 `curl -s https://huggingface.co/api/models/<저장소>/revision/<tag>`가 돌려주는 `sha`다.

1. Dockerfile의 build arg 기본값 수정
2. `make local FUNCTION=<함수> ENV_FILE=.env.dev`로 이미지 빌드와 요청 처리 확인
3. `make check`, `make test` 통과 확인
4. 이 README의 모델 표를 갱신하고 PR 생성, `dev` merge
5. release PR을 merge하면 deploy 워크플로가 새 이미지를 dev Lambda에 반영

기본값을 고치기 전에 다른 버전을 시험하려면 build arg를 넘겨 빌드한다.

```sh
docker build --target mimic-judgment --build-arg MIMIC_JUDGMENT_MODEL_REVISION=<커밋> -t buddybird-audio-ai:mimic-judgment .
```

## 컨테이너

Dockerfile 하나에 이미지 두 개를 target으로 둔다.
target을 고르면 BuildKit은 그 target에 필요한 stage만 빌드한다.

| target | handler | 들어가는 것 |
| --- | --- | --- |
| `parrot-detection` | `app.parrot_detection.handler.handler` | `parrot-detection` 그룹 의존성, 앵무새 소리 판별 모델 |
| `mimic-judgment` | `app.mimic_judgment.handler.handler` | `mimic-judgment` 그룹 의존성, 모사 판정 모델, ffmpeg 연결 |

빌드 stage는 다음과 같다.

| stage | 하는 일 | 다시 실행되는 경우 |
| --- | --- | --- |
| `uv` | base 이미지에 uv 설치 | base 이미지 digest 변경 |
| `requirements` | `uv export`로 이미지별 requirements 파일 생성 | `pyproject.toml`, `uv.lock` 변경. 결과 파일 내용이 같으면 다음 stage는 cache 사용 |
| `model-download` | `model-download` 그룹(huggingface-hub, onnx) 설치 | 그룹의 잠금 버전 변경 |
| `parrot-detection-packages`, `mimic-judgment-packages` | 이미지별 의존성을 `uv pip install --target`으로 설치 | 그 이미지의 requirements 내용 변경 |
| `parrot-detection-model`, `mimic-judgment-model` | `scripts/`의 스크립트로 모델 다운로드 | 그 모델의 build arg나 스크립트 변경 |

- base 이미지 `public.ecr.aws/lambda/python:3.12-arm64`는 digest로 고정한다. tag로 받으면 AWS가 tag를 새 이미지로 바꿀 때마다 GitHub Actions 빌드가 의존성 설치와 모델 다운로드를 처음부터 다시 한다. base 이미지를 바꿀 때는 `docker buildx imagetools inspect public.ecr.aws/lambda/python:3.12-arm64`로 digest를 확인해 `LAMBDA_BASE_IMAGE` 기본값을 고친다.
- 최종 이미지에는 uv, uv 캐시, HuggingFace 캐시, 원본 Perch, onnx가 들어가지 않는다.

크기와 빌드 시간은 2026-10-18 Apple Silicon에서 cache 없이 빌드해 쟀다.

| target | 압축 크기 | 의존성 layer | 모델 layer | 빌드 시간 |
| --- | --- | --- | --- | --- |
| `parrot-detection` | 0.353 GB | 400 MB | 45 MB | 25초 |
| `mimic-judgment` | 1.285 GB | 1.56 GB | 838 MB | 54초 |

프로젝트 버전만 바꾼 빌드는 두 target 모두 1초였고, 의존성 설치와 모델 다운로드를 다시 하지 않았다.
`MIMIC_JUDGMENT_MODEL_REVISION`만 바꾼 빌드는 `mimic-judgment-model` stage만 다시 실행했다.

### ECR 이미지 배포

[release 워크플로](.github/workflows/release.yml)는 `dev`에 push하면 release-please를 실행한다.
릴리스가 만들어지면 [deploy 워크플로](.github/workflows/deploy.yml)를 호출한다.
`main`에 push해도 deploy 워크플로가 실행된다.
deploy 워크플로는 함수마다 job을 하나씩 나란히 실행한다.

| 설정 | 앵무새 소리 판별 | 모사 판정 |
| --- | --- | --- |
| ECR 저장소 | `jn-buddybird-parrot-detection` | `jn-buddybird-mimic-judgment` |
| Lambda 함수 | `jn-buddybird-parrot-detection-<env>` | `jn-buddybird-mimic-judgment-<env>` |
| Dockerfile target | `parrot-detection` | `mimic-judgment` |
| GitHub Actions cache scope | `parrot-detection` | `mimic-judgment` |

- 실행 환경: `ubuntu-24.04-arm`
- 인증: OIDC, 역할 `jn-buddybird-audio-ai-deploy`
- 이미지 태그: `pyproject.toml`의 버전
- `dev`: 같은 버전 태그가 ECR에 없는지 확인하고 arm64 이미지를 빌드해 push한 뒤 dev Lambda의 이미지를 변경한다
- `main`: 같은 버전 태그가 ECR에 있는지 확인하고 prod Lambda의 이미지를 변경한다. 이미지를 다시 빌드하지 않는다
- 한 함수의 job이 실패해도 다른 함수의 job은 계속 진행한다
- 이미지는 `provenance: false`로 빌드한다. Lambda는 여러 플랫폼 이미지와 provenance 증명이 붙은 이미지 목록을 받지 않는다
- 함수마다 배포 시작과 결과를 Slack으로 알린다. 필요한 저장소 secret: `SLACK_WEBHOOK_URL`
- 알림의 커밋 목록은 최대 20개이며, 생략 안내와 전체 변경 내역 링크를 포함해 3,000자 이내로 제한한다. 초과하면 오래된 커밋부터 줄 단위로 생략한다
- Slack 알림 전송이 실패해도 배포는 계속 진행한다. 알림이 없을 때는 GitHub Actions 실행 결과로 배포 성공 여부를 확인한다
- release-please는 `uv.lock`의 프로젝트 버전을 올리지 않는다. 빌드와 CI는 `--frozen`으로 설치해 이 차이로 실패하지 않는다

#### 첫 이미지

Lambda는 만들 때 이미지가 ECR에 있어야 한다.
aws-infra가 `dev-bootstrap`, `prod-bootstrap` 태그로 Lambda를 만들기 전에, ECR에 push할 수 있는 자격 증명으로 로컬에서 두 저장소에 한 번씩 push한다.

```sh
REGISTRY=198252712951.dkr.ecr.ap-northeast-2.amazonaws.com
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin "$REGISTRY"
for function in parrot-detection mimic-judgment; do
  docker buildx build --platform linux/arm64 --provenance=false --push --target "$function" \
    -t "$REGISTRY/jn-buddybird-$function:dev-bootstrap" \
    -t "$REGISTRY/jn-buddybird-$function:prod-bootstrap" .
done
```

- ECR 태그는 IMMUTABLE이라 두 태그는 저장소마다 한 번만 push할 수 있다

## 검사

| 명령 | 실행 내용 |
| --- | --- |
| `make check` | `ruff check --fix`, `ruff format --check`, `mypy` |
| `make test` | `pytest` |

- `make check`: 자동 수정 가능한 Ruff 위반을 파일에 바로 반영
- Ruff 규칙: `pyproject.toml`의 `[tool.ruff.lint]`. buddybird-api와 같은 규칙에서 FastAPI 전용 규칙을 뺐고, 한 줄은 120자
- mypy 설정: `pyproject.toml`의 `[tool.mypy]`
  - strict 모드
  - 검사 대상: `app`, `scripts`, `tests`
- pytest 설정: `pytest.ini`
  - `DeprecationWarning` 숨김
  - Slack 알림 테스트 실행에는 Bash와 `jq`가 필요. 실제 Slack 전송 없이 액션이 생성한 JSON을 검증
- GitHub Actions: `dev`와 `main` 대상 PR에서 `lint`, `test` 실행
  - `lint` 작업: `ruff check`, `ruff format --check`, `mypy`
  - 작업 실패 시 Slack 알림
  - 필요한 저장소 secret: `SLACK_WEBHOOK_URL`

로컬에서 CI와 같은 검사를 수행하려면 다음 명령을 실행한다.

```sh
uv run --frozen --only-dev ruff check
uv run --frozen --only-dev ruff format --check
uv run --frozen mypy
uv run --frozen pytest
```

특정 테스트만 실행하려면 `make test ARGS="tests/parrot_detection/test_calls.py -q"`를 사용한다.

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
- BB-638
- BB-651
