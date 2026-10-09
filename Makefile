.PHONY: setup test local check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

# 환경 변수 파일. 예: make local ENV_FILE=.env.dev
ENV_FILE ?= .env

local:
	docker build -t buddybird-audio-ai:local .
	docker run --rm -p 8080:8080 $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE)) -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN buddybird-audio-ai:local

check:
	uv run ruff check --fix
	uv run ruff format --check
	uv run mypy
