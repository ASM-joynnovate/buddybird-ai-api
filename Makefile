.PHONY: setup test local check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

# 실행할 이미지, 환경 변수 파일. 예: make local IMAGE=mimic-judgment ENV_FILE=.env.dev
IMAGE ?= parrot-detection
ENV_FILE ?= .env

local:
	docker build -f Dockerfile.$(IMAGE) -t buddybird-audio-ai:$(IMAGE) .
	docker run --rm -p 8080:8080 $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE)) buddybird-audio-ai:$(IMAGE)

check:
	uv run ruff check --fix
	uv run ruff format --check
	uv run mypy
