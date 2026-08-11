# Backend image for the ticket system: FastAPI API, RQ worker, and RQ cron
# all start from this ONE image with different commands (see compose.yaml).
#
# Mental model: a Dockerfile is a recipe. Each instruction produces a cached
# "layer". `docker build` reuses a layer if nothing it depends on changed —
# which is why the dependency install comes BEFORE copying the source code.

# Base image: official Python on a slim Debian. "slim" skips compilers and
# docs we don't need, keeping the image small (fewer MB to push, fewer CVEs).
FROM python:3.13-slim

# Don't write .pyc files inside the container (they're useless there) and
# send Python output straight to the container logs without buffering —
# `docker logs` shows print/log output in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# LAYER CACHING RULE: requirements.txt changes rarely, source code changes
# constantly. Copying requirements first means `pip install` is only re-run
# when dependencies actually change — not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the application itself. .dockerignore keeps secrets (keys/, .env),
# the venv, and local databases OUT of this copy.
COPY main.py bootstrap_superadmin.py alembic.ini ./
COPY src ./src
COPY scripts ./scripts
COPY alembic ./alembic

# SECURITY: containers run as root by default. A compromised process running
# as root inside the container is one mistake away from escaping it, so we
# create an unprivileged user and run as it. Production standard practice.
RUN useradd --create-home appuser
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads
USER appuser

# Documentation only — the actual port mapping happens in compose.yaml.
EXPOSE 8000

# 0.0.0.0, not 127.0.0.1: inside a container, 127.0.0.1 is the container's own
# loopback, so nothing outside could ever reach the API. Binding to 0.0.0.0
# listens on the container's network interface, and compose publishes it.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
