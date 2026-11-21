# syntax=docker/dockerfile:1
# uv multi-stage build; meritum-core is fetched over SSH:
#   docker build --ssh default .                       # local, your ssh-agent
#   docker build --ssh default=$RUNNER_TEMP/core_key .  # deploy, read-only deploy key
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 UV_PYTHON_DOWNLOADS=0
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
 && rm -rf /var/lib/apt/lists/*
COPY deploy/github_known_hosts /etc/ssh/ssh_known_hosts
WORKDIR /app
RUN --mount=type=ssh --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=ssh --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

FROM python:3.14-slim-trixie
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER nonroot
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=2)"]
# X-Forwarded-* is trusted only from FORWARDED_ALLOW_IPS (the deploy sets the gateway network).
CMD ["uvicorn", "--factory", "meritum_backend.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
