FROM public.ecr.aws/lambda/python:3.12-arm64 AS uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

RUN pip install --no-cache-dir uv==0.12.10

FROM uv AS requirements

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --group mimic --no-emit-project --emit-index-url -o requirements.txt
RUN uv export --frozen --no-dev --only-group build --no-emit-project -o build-requirements.txt

FROM uv AS packages

COPY --from=requirements /build/requirements.txt ./
RUN uv pip install --index-strategy unsafe-best-match --target /opt/packages -r requirements.txt

FROM uv AS models

COPY --from=requirements /build/build-requirements.txt ./
RUN uv pip install --system -r build-requirements.txt

COPY app/__init__.py ./app/
COPY app/parrot_sound/__init__.py app/parrot_sound/download.py ./app/parrot_sound/
RUN python -m app.parrot_sound.download

COPY app/mimic/__init__.py app/mimic/download.py ./app/mimic/
RUN python -m app.mimic.download

FROM public.ecr.aws/lambda/python:3.12-arm64

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NUMBA_CACHE_DIR=/tmp/numba-cache

COPY --from=packages /opt/packages ${LAMBDA_TASK_ROOT}
RUN ln -s "$(PYTHONPATH=${LAMBDA_TASK_ROOT} python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" /usr/local/bin/ffmpeg
COPY --from=models /var/task/models ${LAMBDA_TASK_ROOT}/models
COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY app ${LAMBDA_TASK_ROOT}/app
RUN python -m compileall -q ${LAMBDA_TASK_ROOT}/app

CMD ["app.handler.handler"]
