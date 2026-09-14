# buddybird-ai-api

Python 3.12와 uv로 FastAPI 서버를 실행하고 기본 API를 확인하는 프로젝트다.
현재 제공하는 API는 헬스체크용 `/api/healthz`다. onset 분석 API와 AI 모델 연결은 후속 구현 대상이다.

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

개발 서버를 실행한다. 포트 기본값은 8000이다.

```sh
make local
make local port=9000
```

별도 터미널에서 헬스체크 API를 호출한다.

```sh
curl --fail http://127.0.0.1:8000/api/healthz
```

정상 응답은 HTTP 200이다.

```json
{"status":"ok"}
```

| 경로 | 용도 |
| --- | --- |
| `/api/healthz` | 서버 응답 확인 |
| `/docs` | 대화형 API 문서 |
| `/openapi.json` | OpenAPI 명세 |

`/api/healthz`는 분석 준비 상태나 외부 서비스 연결 상태를 검사하지 않는다.
개발 서버 종료는 `Ctrl+C`를 사용한다.

## 응답 형식

buddybird-api와 같은 경로 규약과 응답 형식을 사용한다.

- 경로: 모든 경로에 `/api` prefix
- 도메인 라우터 경로: `/api/v1/<도메인>`

성공 응답은 `BaseResponse` 형식이다.

```json
{"message": "", "data": null, "meta": null}
```

`/api/healthz`는 `BaseResponse` 없이 `{"status":"ok"}`를 반환한다.

실패 응답은 전역 예외 핸들러가 `error_code`와 `message` 형식으로 반환한다.

```json
{"error_code": "COMMON__RESOURCE_NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}
```

| 상황 | HTTP 상태 | `error_code` |
| --- | --- | --- |
| `CustomError` 발생 | 예외에 지정한 값, 기본값 400 | 예외에 지정한 값, 기본값 `COMMON__BAD_REQUEST` |
| 요청값 검증 실패 | 422 | `COMMON__REQUEST_VALIDATION_ERROR` |
| 반환값 검증 실패 | 422 | `COMMON__RESPONSE_VALIDATION_ERROR` |
| 처리하지 않은 예외 | 500 | `COMMON__INTERNAL_SERVER_ERROR` |

- 새 에러: `CustomError` 상속 후 `code`, `error_code`, `message` 정의
- `error_code` 형식: `도메인__이유`
- 실패 응답의 `detail`: 미포함, buddybird-api 운영 환경 응답 기준
- 없는 경로의 404 응답: FastAPI 기본 형식 `{"detail":"Not Found"}` 유지, buddybird-api와 같은 동작

## 검사

| 명령 | 실행 내용 |
| --- | --- |
| `make check` | `ruff check --fix`, `ruff format --check`, `mypy` |
| `make test` | `pytest` |

- `make check`: 자동 수정 가능한 Ruff 위반을 파일에 바로 반영
- Ruff 규칙: `pyproject.toml`의 `[tool.ruff.lint]`
- mypy 설정: `pyproject.toml`의 `[tool.mypy]`
  - strict 모드
  - pydantic 플러그인
  - 검사 대상: `app`, `core`, `tests`
- pytest 설정: `pytest.ini`
  - `DeprecationWarning` 숨김
  - Starlette `TestClient`의 httpx 사용 경고: `UserWarning` 계열이라 계속 표시
- GitHub Actions: `dev`와 `main` 대상 PR에서 `lint`, `test` 실행
  - `lint` 작업: `ruff check`, `ruff format --check`, `mypy`
  - 작업 실패 시 Slack 알림
  - 필요한 저장소 secret: `SLACK_WEBHOOK_URL`
- 로컬 확인 환경: Python 3.12.13, uv 0.12.10
- 로컬 확인 결과: Ruff 통과, mypy 통과, 테스트 4개 통과, `make local` 실행 후 `/api/healthz` HTTP 200
- GitHub Actions 실행 결과: PR #1에서 `lint`, `test` 통과

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

- [BB-493](https://daheehyeok.atlassian.net/browse/BB-493)
- [BB-494](https://daheehyeok.atlassian.net/browse/BB-494)
- [BB-495](https://daheehyeok.atlassian.net/browse/BB-495)
- [BB-498](https://daheehyeok.atlassian.net/browse/BB-498)
