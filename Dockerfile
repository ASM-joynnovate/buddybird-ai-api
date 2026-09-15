FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./

RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache-dir -e .

COPY app ./app

ENV PYTHONUNBUFFERED=1
ENV MODE=web
ENV TIMEZONE=Asia/Seoul

CMD sh -c 'if [ "$MODE" = "batch" ]; then python -m app.batch "$TIMEZONE"; else python -m uvicorn app.main:app --host 0.0.0.0 --port 8000; fi'
