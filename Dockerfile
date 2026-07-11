# jamak-ouroboros — cloud review app (ADR-0007 path B).
# The GPU pipeline stays local; this image serves ONLY the review web app +
# JSON API. It never runs STT, so no CUDA / faster-whisper runtime is needed
# (the base deps still pull ctranslate2, a small CPU wheel — that's fine).
#
# Two stages: build the React frontend with Node, then serve it from Python.

# --- Stage 1: build the frontend (produces dist/) ------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY src/jamak/web/frontend/package.json src/jamak/web/frontend/package-lock.json ./
RUN npm ci
COPY src/jamak/web/frontend/ ./
RUN npm run build

# --- Stage 2: python app -------------------------------------------------------
FROM python:3.12-slim
# uv for fast, reproducible installs (matches local dev)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1

# deps first (layer-cached until pyproject/lock change). No project, no dev,
# no CUDA extra — cloud never transcribes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# app source + the frontend built in stage 1
COPY src/ ./src/
COPY --from=frontend /app/frontend/dist ./src/jamak/web/frontend/dist
RUN uv sync --frozen --no-dev

# Railway injects $PORT. Bind 0.0.0.0 so the platform can reach the app;
# HTTPS + the app's own login cookie are the auth layers (set JAMAK_* env).
EXPOSE 8000
CMD uv run jamak serve --host 0.0.0.0 --port ${PORT:-8000} --backup-hours 0
