ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE} AS pointcloud-source
WORKDIR /src
COPY scripts/prepare_pointcloud_tools.py /src/scripts/prepare_pointcloud_tools.py
RUN python scripts/prepare_pointcloud_tools.py --web --source

FROM debian:trixie-slim AS pointcloud-converter
RUN apt-get update && apt-get install -y --no-install-recommends cmake make g++ libtbb-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=pointcloud-source /src/var/pointcloud-tools/source/PotreeConverter-2.1.5 /src
RUN cmake -S /src -B /src/build && cmake --build /src/build --parallel 2 \
    && mkdir -p /opt/potree/lib \
    && cp /src/build/PotreeConverter /opt/potree/ \
    && cp /src/build/liblaszip.so* /opt/potree/lib/ \
    && cp -r /src/build/licenses /opt/potree/

FROM node:24-bookworm-slim AS workbench
WORKDIR /src/apps/workbench
RUN npm install --global pnpm@10.32.1
COPY packages/globe-sdk/ /src/packages/globe-sdk/
COPY packages/ontology-ui/ /src/packages/ontology-ui/
COPY configs/ontology/ /src/configs/ontology/
# Type-check the development preview; this fixture is not copied to runtime.
COPY contracts/examples/spatial-registration-campus.json /src/contracts/examples/spatial-registration-campus.json
COPY apps/workbench/ ./
COPY --from=pointcloud-source /src/apps/workbench/public/assets/potree-1.8.2 /src/apps/workbench/public/assets/potree-1.8.2
RUN pnpm install --frozen-lockfile && pnpm build

FROM ${PYTHON_IMAGE}
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
LABEL org.opencontainers.image.title="CoSpace" \
      org.opencontainers.image.source="https://github.com/vxture/vxture-cospace" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    COSPACE_POTREE_CONVERTER=/opt/potree/PotreeConverter LD_LIBRARY_PATH=/opt/potree/lib
WORKDIR /app
# Apply available distribution security fixes before installing the locked runtime.
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libtbb12 \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/linux/requirements.lock /app/deploy/linux/requirements.lock
COPY deploy/linux/ifc-requirements.lock /app/deploy/linux/ifc-requirements.lock
# pip's vendored build/download libraries are unnecessary in the running product.
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /app/deploy/linux/requirements.lock \
    && python -m venv /opt/ifc \
    && /opt/ifc/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes \
        -r /app/deploy/linux/ifc-requirements.lock \
    && /opt/ifc/bin/pip uninstall --yes pip \
    && pip uninstall --yes pip \
    && install -d -m 0700 -o 10001 -g 10001 /ifc-ipc /ifc-ready /data/runtime
COPY packages /app/packages
COPY experiments/scripts /app/experiments/scripts
COPY experiments/templates/*.html /app/experiments/templates/
COPY contracts/schemas /app/contracts/schemas
COPY configs/ontology /app/configs/ontology
COPY --from=pointcloud-converter /opt/potree /opt/potree
COPY --from=workbench /src/apps/workbench/dist /app/apps/workbench/dist
COPY deploy/linux/healthcheck.py /app/deploy/linux/healthcheck.py
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "deploy/linux/healthcheck.py"]
ENTRYPOINT ["python", "-m", "experiments.scripts.production_workbench"]
CMD ["run"]
