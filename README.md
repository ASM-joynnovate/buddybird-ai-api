# buddybird-ai-api

Python 3.12와 uv로 FastAPI 서버를 실행하고 기본 API를 확인하는 프로젝트다.
현재 제공하는 API는 서버 상태 확인용 `/health`다. onset 분석 API와 AI 모델 연결은 후속 구현 대상이다.

## 실행

- 준비 환경: Python 3.12, uv
- 명령 실행 위치: 저장소 최상위 디렉터리

`uv.lock`에 기록된 의존성을 설치한다.

```sh
uv sync --locked
```

개발 서버를 실행한다.

```sh
uv run --no-sync uvicorn app.main:app --reload
```

별도 터미널에서 상태 확인 API를 호출한다.

```sh
curl --fail http://127.0.0.1:8000/health
```

정상 응답은 HTTP 200이다.

```json
{"status":"ok"}
```

| 경로 | 용도 |
| --- | --- |
| `/health` | 서버 응답 확인 |
| `/docs` | 대화형 API 문서 |
| `/openapi.json` | OpenAPI 명세 |

`/health`는 분석 준비 상태나 외부 서비스 연결 상태를 검사하지 않는다.
개발 서버 종료는 `Ctrl+C`를 사용한다.

## 검사

의존성 설치 후 코드 검사, 형식 검사, 기본 API 테스트를 실행한다.

```sh
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest
```

- 기본 API 테스트: `/health`, `/docs`, `/openapi.json` 응답 확인
- GitHub Actions: `dev`와 `main` 대상 PR에서 `lint`, `test` 실행
- 로컬 확인 환경: Python 3.12.13, uv 0.12.10
- 로컬 확인 결과: Ruff 통과, 테스트 1개 통과, 실제 서버 `/health` HTTP 200
- 알려진 경고: Starlette TestClient의 httpx 사용과 AnyIO BlockingPortal alias에서 deprecated 경고 2개 발생
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
