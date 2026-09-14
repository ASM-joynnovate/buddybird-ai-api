.PHONY: setup test local check


setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest $(ARGS)

local:
	@if [ -n "$(port)" ]; then \
		uv run fastapi dev --port $(port) app/main.py; \
	else \
		uv run fastapi dev --port 8000 app/main.py; \
	fi

check:
	uv run ruff check --fix
	uv run ruff format --check
