FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

FROM python:3.13-slim

# libgomp1 is required at runtime by the OpenModelica-generated FMU
# (binaries/linux64/SlotlessPMSM_abc.so links against OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app /app
COPY ./src ./src
COPY ./config ./config
COPY ./assets ./assets
COPY ./modelica/SlotlessPMSM_abc.fmu ./modelica/SlotlessPMSM_abc.fmu

COPY ./compose/control/start /start
RUN chmod +x /start

ENV DASH_HOST=0.0.0.0
ENV DASH_PORT=8080
ENV DASH_DEBUG=0

EXPOSE 8080

ARG IMAGE_TAG=latest
ENV IMAGE_TAG=${IMAGE_TAG}

CMD ["/start"]
