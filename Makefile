.PHONY: setup test local health proto check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

# 환경 변수 파일. 예: make local ENV_FILE=.env.dev
ENV_FILE ?= .env

local:
	$(if $(port),GRPC_PORT=$(port)) uv run $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE)) python -m app.main

health:
	uv run python -m core.grpc.healthcheck --target 127.0.0.1:$(or $(port),50051)

proto:
	uv run python -m grpc_tools.protoc -I proto \
		--python_out=. --grpc_python_out=. \
		--mypy_out=. --mypy_grpc_out=. \
		proto/buddybird/ai/v1/onset.proto

check:
	uv run ruff check --fix
	uv run ruff format --check
	uv run mypy
