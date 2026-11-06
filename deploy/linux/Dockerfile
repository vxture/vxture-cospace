ARG PYTHON_IMAGE=python:3.14-slim
FROM node:24-bookworm-slim AS workbench
WORKDIR /src/apps/workbench
RUN npm install --global pnpm@10.32.1
COPY apps/workbench/ ./
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
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY deploy/linux/requirements.lock /app/deploy/linux/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/deploy/linux/requirements.lock
COPY packages /app/packages
COPY experiments/scripts /app/experiments/scripts
COPY contracts/schemas /app/contracts/schemas
COPY configs/ontology /app/configs/ontology
COPY --from=workbench /src/apps/workbench/dist /app/apps/workbench/dist
COPY deploy/linux/healthcheck.py /app/deploy/linux/healthcheck.py
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "deploy/linux/healthcheck.py"]
ENTRYPOINT ["python", "-m", "experiments.scripts.production_workbench"]
CMD ["run"]
