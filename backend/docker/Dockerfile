# syntax=docker/dockerfile:1
# Multi-stage build for the LeadPulse backend.
#   * builder stage compiles wheels (kept out of the final image)
#   * runtime stage is slim, runs as a non-root user, and uses an entrypoint
#     that waits for the DB + applies migrations before serving.

# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for psycopg2 / argon2-cffi etc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime libs only (libpq for psycopg2; no compilers).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --create-home app

# Bring in the prebuilt virtualenv.
COPY --from=builder /opt/venv /opt/venv

# App source.
COPY . .

RUN chmod +x docker/entrypoint.sh && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]

# Production default: Gunicorn managing uvicorn workers (override in compose
# for the dev server or the celery worker/beat commands).
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "60"]
