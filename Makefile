.PHONY: setup test local check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

# 실행할 함수와 환경 변수 파일. 예: make local FUNCTION=mimic-judgment ENV_FILE=.env.dev
FUNCTION ?= parrot-detection
ENV_FILE ?= .env

# Lambda 실행 사용자와 같은 비 root 사용자로 실행
local:
	docker build --target $(FUNCTION) -t buddybird-audio-ai:$(FUNCTION) .
	docker run --rm -p 8080:8080 --user 993:990 $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE)) -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN buddybird-audio-ai:$(FUNCTION)

check:
	uv run ruff check --fix
	uv run ruff format --check
	uv run mypy
