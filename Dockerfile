# syntax=docker/dockerfile:1.7
# ---- base image ---------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Minimal system deps for building wheels that don't ship prebuilt for slim.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ---- install dependencies ----------------------------------------------
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---- application --------------------------------------------------------
COPY insta_batch ./insta_batch

# Placeholders that will be mounted as volumes at runtime. Keeping them in the
# image ensures the directories exist even when no volume is attached.
RUN mkdir -p /app/config /app/sessions /app/logs /app/data

EXPOSE 8000

# --factory lets uvicorn call create_app() per-worker.
CMD ["uvicorn", "insta_batch.api.app:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4"]
