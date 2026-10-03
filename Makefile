.PHONY: setup test local check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

# 환경 변수 파일. 예: make local ENV_FILE=.env.dev
ENV_FILE ?= .env

local:
	uv run $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE)) python -m app.main

check:
	uv run ruff check --fix
	uv run ruff format --check
	uv run mypy
