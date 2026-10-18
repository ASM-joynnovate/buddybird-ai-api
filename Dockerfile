# digest로 고정한 Lambda base 이미지
ARG LAMBDA_BASE_IMAGE=public.ecr.aws/lambda/python:3.12-arm64@sha256:9672c8fa29ab0fc33c5b2b22ffe91e99c075d6fc67cc606fcd702a8adee3c5a8

# 앵무새 소리 판별 모델 버전
ARG PARROT_DETECTION_MODEL_TAG=v2.0.0
ARG PARROT_DETECTION_MODEL_VERSION=parrot-sound-gate@v2.0.0

# 모사 판정 모델 버전
ARG MIMIC_JUDGMENT_MODEL_REVISION=b1ba78905267833282c3aceaeb9f0ec02f26f386
ARG MIMIC_JUDGMENT_MODEL_VERSION=parrot-mimicry-judgment@v1.0.0

# 빌드 stage가 사용하는 uv 설치
FROM ${LAMBDA_BASE_IMAGE} AS uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

RUN pip install --no-cache-dir uv==0.12.10

# uv.lock에서 이미지별 requirements 추출
FROM uv AS requirements

COPY pyproject.toml uv.lock ./

RUN uv export --frozen --no-default-groups --group parrot-detection --no-emit-project -o parrot-detection.txt
RUN uv export --frozen --no-default-groups --group mimic-judgment --no-emit-project --emit-index-url -o mimic-judgment.txt
RUN uv export --frozen --only-group model-download --no-emit-project -o model-download.txt

# 모델 다운로드 패키지 설치
FROM uv AS model-download

COPY --from=requirements /build/model-download.txt ./
RUN uv pip install --system -r model-download.txt

# 앵무새 소리 판별 의존성 설치
FROM uv AS parrot-detection-packages

COPY --from=requirements /build/parrot-detection.txt ./
RUN uv pip install --target /opt/packages -r parrot-detection.txt

# 앵무새 소리 판별 모델 다운로드
FROM model-download AS parrot-detection-model

ARG PARROT_DETECTION_MODEL_TAG

COPY scripts/download_parrot_detection_model.py ./
RUN python download_parrot_detection_model.py

# 앵무새 소리 판별 Lambda 이미지
FROM ${LAMBDA_BASE_IMAGE} AS parrot-detection

COPY --from=parrot-detection-packages /opt/packages ${LAMBDA_TASK_ROOT}
COPY --from=parrot-detection-model /var/task/models ${LAMBDA_TASK_ROOT}/models

# 결과 메시지의 model_version
ARG PARROT_DETECTION_MODEL_VERSION
ENV PARROT_DETECTION_MODEL_VERSION=${PARROT_DETECTION_MODEL_VERSION}

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY app ${LAMBDA_TASK_ROOT}/app
RUN python -m compileall -q ${LAMBDA_TASK_ROOT}/app

CMD ["app.parrot_detection.handler.handler"]

# 모사 판정 의존성 설치
FROM uv AS mimic-judgment-packages

COPY --from=requirements /build/mimic-judgment.txt ./
RUN uv pip install --index-strategy unsafe-best-match --target /opt/packages -r mimic-judgment.txt

# 모사 판정 모델 다운로드
FROM model-download AS mimic-judgment-model

ARG MIMIC_JUDGMENT_MODEL_REVISION

COPY scripts/download_mimic_judgment_model.py ./
RUN python download_mimic_judgment_model.py

# 모사 판정 Lambda 이미지
FROM ${LAMBDA_BASE_IMAGE} AS mimic-judgment

ENV HF_HUB_OFFLINE=1 \
    NUMBA_CACHE_DIR=/tmp/numba-cache

COPY --from=mimic-judgment-packages /opt/packages ${LAMBDA_TASK_ROOT}

# m4a를 읽는 ffmpeg를 PATH에 연결
RUN ln -s "$(PYTHONPATH=${LAMBDA_TASK_ROOT} python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" /usr/local/bin/ffmpeg

COPY --from=mimic-judgment-model /var/task/models ${LAMBDA_TASK_ROOT}/models

# 결과 메시지의 model_version
ARG MIMIC_JUDGMENT_MODEL_VERSION
ENV MIMIC_JUDGMENT_MODEL_VERSION=${MIMIC_JUDGMENT_MODEL_VERSION}

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY app ${LAMBDA_TASK_ROOT}/app
RUN python -m compileall -q ${LAMBDA_TASK_ROOT}/app

CMD ["app.mimic_judgment.handler.handler"]
