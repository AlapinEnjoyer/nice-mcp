# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE=python:3.13.11-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.7
FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_BASE} AS app-base

COPY --from=uv /uv /uvx /bin/

ENV PATH="/app/.venv/bin:${PATH}" \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./

FROM app-base AS builder

ENV HF_HOME=/root/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/root/.cache/huggingface/sentence_transformers

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Docker cannot detect remote documentation changes, so callers must change this
# argument to rebuild only the corpus layer.
ARG CORPUS_REFRESH=manual

RUN --mount=type=cache,target=/root/.cache/huggingface \
    printf 'corpus refresh: %s\n' "${CORPUS_REFRESH}" \
    && nice-mcp build-corpus --output-root /data --retrievers bm25,dense --dense-device cpu \
    && nice-mcp validate-corpus /data/current

FROM ${PYTHON_BASE} AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    NICE_MCP_HOST=0.0.0.0 \
    NICE_MCP_PORT=8000 \
    NICE_MCP_SNAPSHOT_PATH=/data/current \
    PYTHONUNBUFFERED=1

RUN groupadd --system nice-mcp \
    && useradd --system --gid nice-mcp --home-dir /nonexistent --shell /usr/sbin/nologin nice-mcp

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /data /data

USER nice-mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).close()"

ENTRYPOINT ["nice-mcp"]
CMD ["serve"]
