# buddybird-ai-api

Python 3.12 기반 앵무 울음 분석 워커다. buddybird-api가 SQS 요청 큐에 넣은 세션 사이클을 분석해 결과 큐로 발행한다.
HTTP나 gRPC로 요청을 받지 않으며, 상태 확인은 [헬스체크](#헬스체크) 명령으로 한다.

## 코드 구조

| 경로 | 역할 |
| --- | --- |
| `app/main.py` | 모델 로딩, SQS 워커 실행과 종료 처리 |
| `app/health.py` | 워커 헬스 상태 기록과 컨테이너 헬스체크 명령 |
| `app/metrics.py` | 사이클 분석 지표를 CloudWatch EMF 로그로 기록 |
| `app/onset/application/` | 사이클 분석, SQS 워커 |
| `app/onset/infra/` | 앵무 소리 판정 모델, S3 오디오 로더, SQS 클라이언트 |
| `app/onset/domain/entities.py` | 울음·분석 결과와 `OnsetCriteria` |
| `app/onset/domain/services.py` | `OnsetAnalyzer`: 울음 검출 |
| `app/onset/domain/emergency.py` | `EmergencyAnalyzer`, `EmergencyCriteria`: 울음별 음역대 판정 |
| `app/onset/domain/loudness.py` | `maxwin_db`, `is_too_quiet`: 앵무 소리 판정 전 음량 게이트 |
| `app/onset/domain/exceptions.py` | 분석 입력·설정 오류 |
| `core/errors.py` | 도메인 오류의 기반 `CustomError` |
| `tests/` | 분석 로직, SQS 워커, 헬스체크, 지표 테스트 |

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

워커를 실행한다. 모델 다운로드·로딩이 끝나면 요청 큐 조회를 시작한다.
요청 큐와 결과 큐 URL은 필수이며, 없으면 시작할 때 오류로 종료한다. 큐 연결 방법은 [로컬 실행](#로컬-실행)을 따른다.
캡처 분석에는 `AUDIO_S3_BUCKET`과 해당 객체를 읽을 수 있는 AWS 인증이 필요하다.

```sh
make local ENV_FILE=.env.dev
```

| 항목 | 값 |
| --- | --- |
| 로그 수준 환경 변수 | `LOG_LEVEL`, 기본값 `INFO` |
| 헬스 상태 파일 환경 변수 | `HEALTH_FILE`, 기본값 임시 디렉터리의 `buddybird-ai-api-health.json` |
| 지표 환경 변수 | `METRICS_ENVIRONMENT`, 지표의 `Environment` 차원 값. 기본값 `local` |

- 종료: `Ctrl+C`. `SIGINT`, `SIGTERM`을 받으면 새 수신을 멈추고 처리 중인 사이클을 최대 25초 기다린다
- 워커가 스스로 끝나면 프로세스를 오류로 종료한다. ECS가 task를 다시 띄운다

## 헬스체크

워커는 상태가 바뀔 때마다 `HealthState`를 헬스 상태 파일에 기록한다.
`python -m app.health`가 파일을 읽어 판정하고, 정상이면 종료 코드 0, 비정상이면 1과 이유를 출력한다.

```sh
uv run python -m app.health
```

| 비정상 조건 | 기준 |
| --- | --- |
| 모델 준비 전 | 모델 로딩이 끝나기 전 |
| SQS 조회 정체 | 대기 상태로 90초 초과. long polling 20초와 수신 실패 재시도 5초에 여유를 둔 값 |
| 사이클 처리 정체 | 처리 상태로 10분 초과. 현재 추정 최대 사이클 처리 시간(약 16초)에 여유를 둔 값 |
| 추론 연속 실패 | 앵무 소리 판정·울음 검출 단계 연속 3회 실패 |
| 상태 파일 없음·손상 | 파일을 읽거나 해석할 수 없음 |

- 대기 상태: SQS 조회 직전에 기록. 처리 상태: 사이클 분석을 시작할 때 기록
- 추론 실패에서 제외: S3 다운로드 실패, 음량 게이트에서 걸린 캡처, 입력 오디오 오류(`InvalidAudioSignalError`). 재시작으로 풀리지 않는 문제라 알람으로 확인한다
- 추론이 한 번 성공하면 연속 실패 수를 0으로 초기화한다
- 시간은 `time.monotonic()`으로 잰다. 같은 호스트의 프로세스끼리 공유되는 시계라 워커와 확인 명령이 같은 기준을 쓴다
- 기준값은 dev 배포 후 `elapsed=` 로그를 보고 조정한다

ECS 작업 정의에 권장하는 설정(aws-infra BB-439):

| 설정 | 값 |
| --- | --- |
| command | `["CMD", "python", "-m", "app.health"]` |
| interval | 15초 |
| timeout | 5초 |
| retries | 3 |
| startPeriod | 120초. 모델 로딩 실측 후 조정 |

## 지표

예외 없이 틀린 값을 내는 모델 이상은 헬스체크로 잡을 수 없다. 워커는 사이클마다 지표를 CloudWatch EMF 형식 JSON 한 줄로 표준 출력에 남기고,
CloudWatch Logs가 이를 네임스페이스 `BuddyBird/AiApi`, 차원 `Environment`의 지표로 추출한다. 별도 IAM 권한은 필요 없다.

| 지표 | 단위 | 값 |
| --- | --- | --- |
| `CycleFailures` | Count | 성공 0, 분석 실패 1. 실패한 사이클은 이 값만 남김 |
| `Captures` | Count | 사이클 캡처 수 |
| `ParrotCaptures` | Count | 앵무 소리로 판정된 캡처 수 |
| `TooQuietCaptures` | Count | 음량 게이트에서 걸린 캡처 수 |
| `CallCount` | Count | 울음 전체 수 합계 |
| `EmergencyCycles` | Count | 위급 캡처가 있으면 1 |
| `CycleSeconds` | Seconds | 사이클 처리 시간 |
| `ScoreMean`, `ScoreStdDev` | None | 음량 게이트를 통과한 캡처의 `score` 평균과 표준편차. 통과한 캡처가 없으면 생략 |

알람 예시(aws-infra BB-439). 임계값은 dev 배포 후 1~2주 데이터를 보고 정한다.

| 알람 | 조건 | 잡는 문제 |
| --- | --- | --- |
| 사이클 실패 | `CycleFailures` 합계 1 이상 | 추론·S3·SQS 오류 |
| 앵무 판정 0% | `Captures` > 0인데 몇 시간 동안 `ParrotCaptures` = 0 | 모델이 전부 앵무 아님으로 판정 |
| score 고정 | `ScoreStdDev`가 0에 가까움 | 모델 출력 고장, 전처리 오류 |
| too_quiet 비율 이탈 | `TooQuietCaptures / Captures`가 평소(약 5.6%)에서 크게 벗어남 | 마이크·녹음 환경 변화 |
| 처리 지연 | `CycleSeconds`가 평소 대비 급증 | CPU 병목, 추론 지연 |

## 도메인 오류

- 새 오류: `CustomError`를 상속하고 `code`, `error_code`, `message`를 정의
- `error_code` 형식: `도메인__이유`

## 울음 분석과 위급 판정

`CycleAnalyzer`는 캡처마다 다음 순서로 분석한다.

```text
S3 다운로드 → 음량 게이트 → 앵무 소리 판정(parrot-sound-gate) → 울음 검출 → 울음별 음역대 판정
```

- 음량 게이트에서 걸리면 이후 단계를 건너뛰고 앵무가 아닌 캡처로 처리한다.
- 울음 검출과 음역대 판정은 앵무 소리로 판정된 캡처에만 한다.

| 용어 | 뜻 | 결과 필드 |
| --- | --- | --- |
| 울음(call) | 울음 검출이 찾은 소리 구간 하나, 음역대 무관 | `call_count` |
| 짹(chirp) | 울음 중 대표 음높이가 위급 음역대 안인 것 | `chirp_count` |

짹은 울음의 일부이므로 `chirp_count`는 항상 `call_count` 이하다.
두 도메인 분석기(울음 검출, 울음별 음역대 판정)는 캡처 하나를 대상으로 한다.

### 음량 게이트

`maxwin_db`는 100 ms 창을 100 ms 간격으로 옮기며 구한 RMS의 최댓값을 dBFS로 돌려준다.
긴 무음 속 짧은 울음이 평균에 희석되지 않도록 전체 RMS 대신 최대 창을 쓴다. 창보다 짧은 캡처는 전체를 한 창으로 본다.

| 기준 | 값 |
| --- | --- |
| 창 길이·간격 | 100 ms |
| `too_quiet` | `maxwin_db` < −39 dBFS, −39.0은 통과 |

- 기준 출처: parrot-mimicry `docs/step1-loudness-gate/spec-step1-loudness-gate.md`, 계산은 `scripts/step2/classify_folder.py`의 `maxwin_db()`와 같다.
- `too_quiet` 캡처 결과: `is_parrot=false`, `score=0.0`, `call_count=0`, `chirp_count=0`. 결과 형식에 별도 필드는 없고, 캡처마다 `capture <id> maxwin_db=<값> too_quiet=<판정>`을 INFO 로그로 남긴다.

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

### 결과의 위급 판정과 울음 수

`CycleAnalyzer`는 각 캡처의 음역대 안 울음 수를 `chirp_count`로 사용한다.
`captured_at` 순서로 처리한 캡처 중 현재 캡처의 `captured_at`부터 30초 전까지의 횟수를 합산하고(30초 경계 포함),
`window_chirp_count >= 7`이면 결과의 `is_emergency`가 true다.
시간 창은 사이클마다 초기화되며, 사이클 사이에 누적되지 않는다.

위급 판정과 별개로, 앵무 소리로 판정된 캡처는 음역대와 관계없이 울음 검출이 찾은 울음 전체 수를 `call_count`로 남긴다.
앵무가 아니거나 음량 게이트에서 걸린 캡처의 `call_count`는 0이다.
분석에 실패한 캡처가 하나라도 있으면 워커는 사이클 결과를 발행하지 않고 요청을 다시 처리한다([처리 규칙](#처리-규칙)).

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

## SQS 사이클 분석

buddybird-api가 세션 사이클 하나를 요청 큐에 넣으면, 워커가 분석해 결과 큐로 발행한다.
모델 로딩이 끝나면 워커가 요청 큐 조회를 시작한다.

| 환경 변수 | 값 |
| --- | --- |
| `SQS_PARROT_SOUND_DETECTION_QUEUE_URL` | 요청 큐 URL. 필수 |
| `SQS_JUDGMENT_RESULT_QUEUE_URL` | 결과 큐 URL. 필수 |
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
| 종료(`SIGTERM`) | 새 수신 중단, 처리 중인 사이클은 최대 25초 대기. 넘기면 요청을 즉시 큐에 반환 |
| 워커가 스스로 종료 | 프로세스를 오류로 종료. ECS가 task를 다시 띄움 |
| 추론 연속 3회 실패 | 헬스체크 비정상. ECS 작업 정의에 헬스체크가 있으면 task 교체(BB-439) |

- 중복 결과: 결과 발행 뒤 요청 삭제 전에 종료되면 같은 결과를 다시 발행. buddybird-api에서 `session_id`, `cycle`, `model_version`으로 중복 제거
- 처리 시간: 사이클마다 `사이클 분석 완료 … elapsed=` 로그

### 로컬 실행

#### dev 큐에 연결

실제 dev SQS와 데이터 버킷을 사용한다. Docker가 필요 없고 dev 버킷 읽기 권한이 있는 AWS 인증(`aws sso login`)이 필요하다.

1. `.env.example`을 `.env.dev`로 복사하고 dev 리전, 버킷, 두 큐 URL을 채운다. 값은 aws-infra 출력이나 AWS 콘솔에서 확인한다.
2. 워커를 실행한다.

```sh
make local ENV_FILE=.env.dev
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
2. `make local ENV_FILE=.env.dev`로 모델 다운로드와 워커 시작 확인
3. `make check`, `make test` 통과 확인
4. 이 README의 모델 표 갱신 후 PR 생성, `dev` merge
5. GitHub Actions `deploy` 워크플로 수동 실행. 이미지 빌드 때 새 모델이 포함됨

## 컨테이너

- 실행 명령: `python -m app.main`
- 헬스체크 명령: `python -m app.health`
- 의존성: `uv sync --locked --no-dev --no-install-project`로 설치
- 이미지 아키텍처: 배포 워크플로에서 `linux/arm64`로 빌드
- 판정 모델: 빌드 때 `python -m app.onset.infra.parrot_gate`로 받아 `HF_HOME=/app/models`에 저장
- 실행 중 HuggingFace 접속: 없음, `HF_HUB_OFFLINE=1`

로컬 이미지 실행과 헬스체크:

```sh
docker build -t buddybird-ai-api:local .
docker run --rm --env-file .env.dev --name buddybird-ai-api buddybird-ai-api:local
# 별도 터미널에서 실행
docker exec buddybird-ai-api python -m app.health
```

- `.env.dev`의 AWS 인증은 컨테이너에 따로 전달해야 한다. 예: `-v ~/.aws:/root/.aws:ro -e AWS_PROFILE=<프로필>`

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
- pytest 설정: `pytest.ini`
  - `DeprecationWarning` 숨김
- GitHub Actions: `dev`와 `main` 대상 PR 또는 수동 실행 시 `lint`, `test` 실행
  - `lint` 작업: `ruff check`, `ruff format --check`, `mypy`
  - 작업 실패 시 Slack 알림
  - 필요한 저장소 secret: `SLACK_WEBHOOK_URL`

검증 결과는 실행 시점의 코드와 환경에 따라 달라진다. 로컬에서 CI와 같은 검사를 수행하려면:

```sh
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
make test
```

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
