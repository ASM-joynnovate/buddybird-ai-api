# buddybird-audio-ai

Python 3.12 기반 앵무 울음 분석 Lambda 함수다.
buddybird-api가 SQS 요청 큐에 넣은 소리를 SQS 트리거로 받아 분석하고, 결과를 결과 큐로 발행한다.
HTTP나 gRPC로 요청을 받지 않는다.

## 코드 구조

| 경로 | 역할 |
| --- | --- |
| `app/handler.py` | Lambda 핸들러. 모델 로딩, SQS 배치 처리, 결과 발행 |
| `app/sound_analyzer.py` | 소리 하나를 S3에서 읽어 음량 게이트, 앵무 소리 판정, 울음 수 계산 |
| `app/parrot_gate.py` | 앵무 소리 판정 모델. 이미지 빌드 때 모델을 받아 가공하는 스크립트 포함 |
| `app/loudness.py` | `maxwin_db`, `is_too_quiet`: 앵무 소리 판정 전 음량 게이트 |
| `app/calls.py` | `detect_calls`, `count_chirps`: 울음 검출과 짹 수 계산 |
| `tests/` | 울음 검출, 음량 게이트, handler 부분 실패, Slack 알림 길이 제한 테스트 |

## 준비

- 준비 환경: Python 3.12, uv, make, Docker
- 명령 실행 위치: 저장소 최상위 디렉터리

의존성을 설치하고 커밋 전 검사 훅을 등록한다.

```sh
make setup
```

`make setup`은 `uv sync`를 실행하고 git `core.hooksPath`를 `.githooks`로 지정한다.
등록한 훅은 커밋할 Python 파일에 `ruff check --fix`와 `ruff format --check`를 실행한다.
포맷 오류가 있으면 `uv run ruff format <파일>`로 수정한 뒤 다시 커밋한다.
CI와 같은 잠금 버전으로 설치하려면 `uv sync --frozen`을 사용한다.

## 실행

Lambda 이미지를 빌드하고 Runtime Interface Emulator(RIE)로 실행한다.
RIE는 베이스 이미지에 들어 있는 로컬 Lambda 실행 서버다.
소리 분석에는 `AUDIO_S3_BUCKET`과 그 버킷을 읽을 수 있는 AWS 임시 자격 증명이 필요하다.

1. `.env.example`을 `.env.dev`로 복사하고 리전, 버킷, 결과 큐 URL을 채운다.
2. 임시 자격 증명을 셸 환경 변수로 내보낸 뒤 실행한다.

```sh
eval "$(aws configure export-credentials --profile <프로필> --format env)"
make local ENV_FILE=.env.dev
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

- 환경 변수는 [SQS 소리 분석](#sqs-소리-분석)의 표를 따른다.
- `make local`은 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`을 컨테이너에 그대로 넘기고 `~/.aws`를 마운트하지 않는다. SSO 프로필은 토큰을 갱신하면서 `~/.aws/sso/cache`에 파일을 쓰므로, 읽기 전용으로 마운트하면 S3 읽기가 모두 실패한다.
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

## 울음 분석

`sound_analyzer.analyze`는 소리마다 다음 순서로 분석한다.

```text
S3 다운로드 → 음량 게이트 → 앵무 소리 판정(parrot-sound-gate) → 울음 검출 → 짹 수 계산
```

- 음량 게이트에서 걸리면 이후 단계를 건너뛰고 앵무가 아닌 소리로 처리한다.
- 울음 검출과 짹 수 계산은 앵무 소리로 판정된 소리에만 한다.

| 용어 | 뜻 | 결과 필드 |
| --- | --- | --- |
| 울음(call) | 울음 검출이 찾은 소리 구간 하나, 음역대 무관 | `call_count` |
| 짹(chirp) | 울음 중 대표 음높이가 4,600~8,000 Hz인 것 | `chirp_count` |

짹은 울음의 일부이므로 `chirp_count`는 항상 `call_count` 이하다.
앵무가 아니거나 음량 게이트에서 걸린 소리의 `call_count`와 `chirp_count`는 0이다.
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

- 기준 출처: parrot-mimicry `docs/step1-loudness-gate/spec-step1-loudness-gate.md`. 계산은 `scripts/step2/classify_folder.py`의 `maxwin_db()`와 같고, `tests/test_loudness.py`의 `reference_maxwin_db`가 그 계산의 사본이다.
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

from app.calls import count_chirps, detect_calls

sample_rate = 16000
times = np.arange(round(0.12 * sample_rate)) / sample_rate
chirp = 0.5 * np.sin(2 * np.pi * 5000 * times)
silence = np.zeros(round(0.15 * sample_rate))
audio = np.tile(np.concatenate([chirp, silence]), 7)

calls = detect_calls(audio, sample_rate)
print(len(calls), count_chirps(audio, sample_rate, calls))  # 7 7
PYTHON
```

## SQS 소리 분석

buddybird-api가 소리 하나를 요청 큐에 넣으면, SQS 트리거가 최대 10개씩 묶어 Lambda를 호출한다.
Lambda는 배치 안에서 최대 4개 소리를 동시에 분석하고, 소리마다 결과 메시지를 결과 큐로 발행한다.

| 환경 변수 | 값 |
| --- | --- |
| `SQS_JUDGMENT_RESULT_QUEUE_URL` | 결과 큐 URL. 필수. 없으면 초기화 단계에서 실패 |
| `AUDIO_S3_BUCKET` | 소리 버킷. 없으면 모든 메시지가 처리 실패 |
| `SQS_ENDPOINT_URL` | 로컬 elasticmq 주소. 운영에서는 비움 |
| `APP_ENV` | Sentry environment. 비우면 `local` |
| `SENTRY_DSN` | buddybird-audio-ai Sentry 프로젝트 DSN. 비우면 Sentry로 보내지 않음 |
| `LOG_LEVEL` | 로그 수준. 기본값 `INFO` |

| Lambda 설정 | 값 |
| --- | --- |
| 이미지 | arm64 컨테이너 이미지 |
| 메모리, 제한 시간 | 4,096 MB, 60초 |
| SQS 트리거 | 배치 10개, `ReportBatchItemFailures`, 최대 동시 실행 10 |
| 요청 큐 | 가시성 시간 360초, 5번 실패하면 DLQ로 이동 |

- Lambda와 SQS 트리거는 aws-infra `buddybird-app`이 만든다

### 요청 메시지

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
- Lambda는 buddybird-api가 보낸 값을 검증하지 않고 그대로 읽는다. `type`도 확인하지 않는다. 필드가 없거나 읽을 수 없으면 그 메시지는 처리 실패다.

### 결과 메시지

```json
{
  "type": "audio.parrot_detected",
  "session_id": "0199…",
  "analyzer_version": "buddybird-audio-ai@0.1.0",
  "analyzed_at": "2026-10-06T14:45:32.153710+00:00",
  "data": [
    {"audio_id": "0199…", "is_parrot": true, "score": 0.93, "call_count": 11, "chirp_count": 4}
  ]
}
```

- 메시지 하나에 요청과 같은 소리 하나를 담는다
- `analyzer_version`: `pyproject.toml`의 `name@version`. buddybird-api는 같은 소리와 같은 `analyzer_version`의 결과를 다시 받으면 무시한다
- `analyzed_at`: 결과를 만든 UTC 시각, ISO 8601, 시간대 포함
- `score`: 앵무 소리 판정 확률. `is_parrot`이 false면 `call_count`와 `chirp_count`는 0
- `call_count`: 울음 전체 수, 음역대 무관
- `chirp_count`: 짹 수

### 처리 규칙

| 상황 | 동작 |
| --- | --- |
| 분석 성공 | 결과 발행. 요청 삭제는 SQS 트리거가 함 |
| 요청을 읽지 못하거나 분석 또는 결과 발행 실패 | 결과 미발행. 그 메시지만 `batchItemFailures`로 돌려주고 같은 배치의 다른 메시지는 영향 없음 |
| 실패한 메시지 | 가시성 시간 360초 뒤 다시 처리. 5번 실패하면 SQS가 DLQ로 옮기고, buddybird-api consumer가 그 소리를 failed로 표시 |
| 60초 제한 시간 초과나 처리하지 못한 예외 | 응답이 없어 배치 전체를 다시 처리. 이미 발행한 결과도 다시 발행 |
| 같은 요청을 다시 처리 | `analyzed_at`만 다른 같은 결과를 발행. buddybird-api가 같은 `analyzer_version` 결과를 무시 |

- 확인 기록(2026-10-06, RIE): 10개 배치는 실패 없이 처리, 없는 키와 JSON이 아닌 본문만 `batchItemFailures`로 반환, 제한 시간 2초에서 30개 중 일부를 발행한 뒤 중단되었고 다시 처리한 결과는 `analyzed_at`만 다름, 배치 안 동시 분석은 최대 4개

## 앵무 소리 판정 모델

| 모델 | HuggingFace 저장소 | 버전 | 파일 |
| --- | --- | --- | --- |
| 판정 | `buddybird-ai/parrot-sound-gate` | `v2.0.0` | `gate-2.0.0.joblib` |
| 임베딩 | `justinchuby/Perch-onnx` | 커밋 `da88bf8` | `perch_v2.onnx`, 409 MB |

- 이미지 빌드 때 두 모델을 받아 `/var/task/models`에 넣는다. Perch는 `embedding` 출력만 남겨 45 MB로 줄인다.
- 실행 중 HuggingFace 접속: 없음. 최종 이미지에는 huggingface-hub가 없음
- HuggingFace 업로드 절차: parrot-mimicry `docs/ops/huggingface.md`

### 모델 버전 올리기

HuggingFace에 새 태그가 올라와도 자동 반영하지 않는다. 버전 고정 후 PR로 교체한다.

1. `app/parrot_gate.py` 수정
   - `_GATE_REVISION`: 새 태그
   - 빌드 스크립트의 판정 파일명: 새 태그의 파일명
   - 빌드 스크립트의 Perch 커밋: 새 태그 `model_manifest.json`에 기록된 Perch 커밋
2. `make local ENV_FILE=.env.dev`로 이미지 빌드와 요청 처리 확인
3. `make check`, `make test` 통과 확인
4. 이 README의 모델 표 갱신 후 PR 생성, `dev` merge
5. release PR을 merge하면 deploy 워크플로가 새 이미지를 dev Lambda에 반영. 버전이 오르므로 `analyzer_version`도 변경됨

## 컨테이너

- 베이스 이미지: `public.ecr.aws/lambda/python:3.12-arm64`
- 핸들러: `app.handler.handler`
- 빌드 단계: uv로 런타임 의존성과 빌드 전용 그룹(`huggingface-hub`, `onnx`)을 설치하고 모델을 받아 가공. 런타임 의존성은 `uv export --frozen --no-dev`와 `uv pip install --target`으로 따로 설치
- 최종 이미지: 런타임 패키지, `app/`, `pyproject.toml`, 가공한 모델 2개. uv, uv 캐시, HuggingFace 캐시, 원본 Perch, onnx는 들어가지 않음
- 크기(2026-10-06): 압축 351 MB, 압축을 푼 레이어 합계 약 1.02 GB. 이전 ECS 워커 이미지는 압축 822 MB
- 초기화: 모듈을 불러올 때 모델을 한 번 올림. RIE에서 0.6~0.9초
- `onnxruntime`을 import할 때 `blkid`, `hostname` 명령을 찾지 못했다는 줄을 stderr에 남긴다. 베이스 이미지에 두 명령이 없어서 생기며, 190개 소리 비교에서 결과에 영향이 없었다.

### ECR 이미지 배포

[release 워크플로](.github/workflows/release.yml)는 `dev`에 push하면 release-please를 실행한다.
릴리스가 만들어지면 [deploy 워크플로](.github/workflows/deploy.yml)를 호출한다.
`main`에 push해도 deploy 워크플로가 실행된다.

| 설정 | 값 |
| --- | --- |
| 실행 환경 | `ubuntu-24.04-arm` |
| ECR 저장소 | `jn-buddybird-audio-ai` |
| 인증 | OIDC, 역할 `jn-buddybird-audio-ai-deploy` |
| 이미지 태그 | `pyproject.toml`의 버전 |
| Lambda 함수 | `dev`는 `jn-buddybird-audio-ai-dev`, `main`은 `jn-buddybird-audio-ai-prod` |

- `dev`: 같은 버전 태그가 ECR에 없는지 확인하고 arm64 이미지를 빌드해 push한 뒤 dev Lambda의 이미지를 변경한다
- `main`: 같은 버전 태그가 ECR에 있는지 확인하고 prod Lambda의 이미지를 변경한다. 이미지를 다시 빌드하지 않는다
- 이미지는 `provenance: false`로 빌드한다. Lambda는 여러 플랫폼 이미지와 provenance 증명이 붙은 이미지 목록을 받지 않는다
- 배포 시작과 결과를 Slack으로 알린다. 필요한 저장소 secret: `SLACK_WEBHOOK_URL`
- 알림의 커밋 목록은 최대 20개이며, 생략 안내와 전체 변경 내역 링크를 포함해 3,000자 이내로 제한한다. 초과하면 오래된 커밋부터 줄 단위로 생략한다
- Slack 알림 전송이 실패해도 배포는 계속 진행한다. 알림이 없을 때는 GitHub Actions 실행 결과로 배포 성공 여부를 확인한다
- release-please는 `uv.lock`의 프로젝트 버전을 올리지 않는다. 빌드와 CI는 `--frozen`으로 설치해 이 차이로 실패하지 않는다

#### 첫 이미지

Lambda는 만들 때 이미지가 ECR에 있어야 한다.
aws-infra가 `dev-bootstrap`, `prod-bootstrap` 태그로 Lambda를 만들기 전에, ECR에 push할 수 있는 자격 증명으로 로컬에서 한 번 push한다.

```sh
REGISTRY=198252712951.dkr.ecr.ap-northeast-2.amazonaws.com
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 --provenance=false --push \
  -t "$REGISTRY/jn-buddybird-audio-ai:dev-bootstrap" \
  -t "$REGISTRY/jn-buddybird-audio-ai:prod-bootstrap" .
```

- ECR 태그는 IMMUTABLE이라 두 태그는 한 번만 push할 수 있다

## 검사

| 명령 | 실행 내용 |
| --- | --- |
| `make check` | `ruff check --fix`, `ruff format --check`, `mypy` |
| `make test` | `pytest` |

- `make check`: 자동 수정 가능한 Ruff 위반을 파일에 바로 반영
- Ruff 규칙: `pyproject.toml`의 `[tool.ruff.lint]`
- mypy 설정: `pyproject.toml`의 `[tool.mypy]`
  - strict 모드
  - 검사 대상: `app`, `tests`
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

특정 테스트만 실행하려면 `make test ARGS="tests/test_calls.py -q"`를 사용한다.

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
