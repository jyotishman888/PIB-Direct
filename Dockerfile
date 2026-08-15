# syntax=docker/dockerfile:1

# ---------- stage 1: build the SPA ----------
# The frontend is baked into the API image so both come off one origin, which
# is what keeps the session cookie first-party (see api/app.py).
FROM node:22-slim AS frontend

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci

# The VITE_* values are compiled into the bundle, so they're build args rather
# than runtime env. Setting them only in the platform's variables is the easy
# mistake: the app boots fine and the login page silently shows nothing.
ARG VITE_GOOGLE_CLIENT_ID=""
ARG VITE_TELEGRAM_CLIENT_ID=""
ARG VITE_API_BASE_URL="/api"
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_TELEGRAM_CLIENT_ID=$VITE_TELEGRAM_CLIENT_ID \
    VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY frontend/ ./
RUN npm run build


# ---------- stage 2: the app ----------
FROM python:3.12-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # sentence-transformers caches model weights here; baking them into the
    # image avoids a download on every cold start.
    HF_HOME=/opt/hf

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install the CPU build of torch *before* resolving everything else. On Linux
# the default PyPI torch pulls the CUDA stack — gigabytes of NVIDIA libraries
# this app can never use, since embedding runs on CPU. Doing it first means
# the CUDA wheel is never selected during the main resolve.
RUN uv pip install --system --no-cache \
      --index-url https://download.pytorch.org/whl/cpu \
      torch

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache .

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

# The built SPA, where api/app.py::_static_dir looks for it.
COPY --from=frontend /frontend/dist/ ./src/pib_agent/static/

# Pre-download the embedding model so the first similarity pass isn't also a
# ~90MB download. Failure here must not break the build — the model will just
# be fetched at runtime instead.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')" || echo "model prefetch skipped"

EXPOSE 8000

# Railway injects PORT; default keeps `docker run` working unchanged.
ENV API_HOST=0.0.0.0

# Migrations run here, in the start command, rather than as a build or
# pre-deploy step. Railway's private network is runtime-only, so a migration
# run any earlier can't reach the database at all — its own docs say to do it
# this way. `pib-agent migrate` waits for the network before applying.
#
# Only this service runs migrations: the bot overrides the start command, so
# the two can't race each other on a fresh database.
CMD ["sh", "-c", "pib-agent migrate && pib-agent serve --host 0.0.0.0 --port ${PORT:-8000}"]
