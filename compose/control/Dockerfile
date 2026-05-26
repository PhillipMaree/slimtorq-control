# Stage 1 — build the Next.js static export.
FROM node:22-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
# `output: 'export'` in next.config.mjs writes the static bundle to ./out.

# Stage 2 — resolve Python deps with uv.
FROM python:3.13-slim AS py-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Stage 3 — runtime: Python + FMU + prebuilt frontend bundle. Single port.
FROM python:3.13-slim

# libgomp1 is required at runtime by the OpenModelica-generated FMU
# (binaries/linux64/SlotlessPMSM_abc.so links against OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=py-builder /app /app
COPY ./src ./src
COPY ./config ./config
COPY ./modelica/SlotlessPMSM_abc.fmu ./modelica/SlotlessPMSM_abc.fmu
COPY --from=frontend-builder /build/out ./frontend/out

COPY ./compose/control/start /start
RUN chmod +x /start

# Server / paths come from config/config.yaml — env vars below only override
# container-specific paths (writable volume mount + bundled frontend bundle).
ENV ARTIFACTS__DIR=/data/artifacts
ENV FRONTEND__DIST_DIR=/app/frontend/out

EXPOSE 8000

ARG IMAGE_TAG=latest
ENV IMAGE_TAG=${IMAGE_TAG}

CMD ["/start"]
