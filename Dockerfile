FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/app/models

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.10

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY core ./core

ENV PATH="/app/.venv/bin:$PATH"

# 판정 모델을 이미지에 넣고, 실행 중에는 HuggingFace에 접속하지 않는다.
RUN python -m app.onset.infra.parrot_gate
ENV HF_HUB_OFFLINE=1

CMD ["python", "-m", "app.main"]
