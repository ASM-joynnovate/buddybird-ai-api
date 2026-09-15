FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.12.10

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY core ./core

ENV PATH="/app/.venv/bin:$PATH" \
    MODE=web \
    TIMEZONE=Asia/Seoul

CMD sh -c 'if [ "$MODE" = "batch" ]; then python -m app.batch "$TIMEZONE"; else python -m uvicorn app.main:app --host 0.0.0.0 --port 8000; fi'
