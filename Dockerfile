FROM public.ecr.aws/lambda/python:3.12-arm64 AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

RUN pip install --no-cache-dir uv==0.12.10

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group build --no-install-project
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt
RUN uv pip install --target /opt/packages -r requirements.txt

COPY app/__init__.py app/parrot_gate.py ./app/
RUN .venv/bin/python -m app.parrot_gate

FROM public.ecr.aws/lambda/python:3.12-arm64

COPY --from=build /opt/packages ${LAMBDA_TASK_ROOT}
COPY --from=build /var/task/models ${LAMBDA_TASK_ROOT}/models
COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY app ${LAMBDA_TASK_ROOT}/app
RUN python -m compileall -q ${LAMBDA_TASK_ROOT}/app

CMD ["app.handler.handler"]
