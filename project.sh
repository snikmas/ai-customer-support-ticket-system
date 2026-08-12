#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"

cd "${PROJECT_DIR}"

usage() {
    cat <<'EOF'
Usage: ./project.sh [start|status|logs|demo-data|stop]

  start   Build and start the complete project, then wait for health checks.
          This is the default when no command is provided.
  status  Show the current state of every project container.
  logs    Follow logs from all project services. Press Ctrl+C to stop viewing.
  demo-data Create synthetic local demo records; requires DEMO_MODE=1 and
            DEMO_PASSWORD.
  stop    Gracefully stop the project without deleting its database volume.
EOF
}

require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is not installed or is not available in PATH." >&2
        exit 1
    fi

    if ! docker compose version >/dev/null 2>&1; then
        echo "The Docker Compose plugin is not available." >&2
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "The Docker daemon is not running or your user cannot access it." >&2
        exit 1
    fi
}

require_configuration() {
    if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
        echo "Missing ${PROJECT_DIR}/.env" >&2
        echo "Create it with: cp .env.example .env" >&2
        echo "Then replace the example passwords before starting the project." >&2
        exit 1
    fi

    if [[ ! -f "${PROJECT_DIR}/keys/private.pem" || ! -f "${PROJECT_DIR}/keys/public.pem" ]]; then
        echo "JWT key files are missing from ${PROJECT_DIR}/keys/." >&2
        echo "Both private.pem and public.pem are required by the API." >&2
        exit 1
    fi

    local refresh_token_secret
    refresh_token_secret="$(sed -n 's/^REFRESH_TOKEN_SECRET=//p' "${PROJECT_DIR}/.env")"
    if [[ -z "${refresh_token_secret}" || "${refresh_token_secret}" == "replace-with-a-long-random-refresh-secret" ]]; then
        echo "Missing REFRESH_TOKEN_SECRET in ${PROJECT_DIR}/.env" >&2
        echo "Generate one with: openssl rand -hex 32" >&2
        echo "Store it only in .env; never commit or paste it into screenshots." >&2
        exit 1
    fi

    docker compose config --quiet
}

ensure_superadmin() {
    local bootstrap_state

    bootstrap_state="$(docker compose exec -T api python - <<'PY'
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants import Role
from src.core.security import verify_password
from src.db.engine import engine
from src.db.models import User

nickname = os.environ.get("SUPERADMIN_NICKNAME", "")
email = os.environ.get("SUPERADMIN_EMAIL", "")
password = os.environ.get("SUPERADMIN_PASSWORD", "")

with Session(engine) as session:
    user_count = session.scalar(select(func.count()).select_from(User)) or 0
    configured_user = session.scalar(
        select(User).where(User.nickname == nickname, User.email == email)
    )

if user_count == 0:
    print("empty")
elif (
    configured_user is not None
    and configured_user.role is Role.SUPER_ADMIN
    and verify_password(password, configured_user.password)
):
    print("ready")
else:
    print("configuration_mismatch")
PY
)"

    case "${bootstrap_state}" in
        empty)
            echo "Creating the initial superadmin from .env..."
            docker compose exec -T api python bootstrap_superadmin.py
            ;;
        ready)
            echo "Configured superadmin is ready."
            ;;
        configuration_mismatch)
            echo "Warning: the database already contains users, but its superadmin" >&2
            echo "does not match the current SUPERADMIN_* values in .env." >&2
            echo "The launcher will not overwrite an existing account." >&2
            ;;
        *)
            echo "Could not determine the superadmin bootstrap state." >&2
            exit 1
            ;;
    esac
}

start_project() {
    require_configuration

    echo "Starting PostgreSQL, Redis, migrations, API, worker, cron, and frontend..."
    if ! docker compose up --build --detach --wait --wait-timeout 180; then
        echo >&2
        echo "The stack did not become healthy. Current status:" >&2
        docker compose ps >&2 || true
        echo >&2
        echo "Recent service logs:" >&2
        docker compose logs --tail=80 api worker cron db redis frontend migrate >&2 || true
        exit 1
    fi

    ensure_superadmin
    docker compose ps
    echo
    echo "Project is ready:"
    echo "  Frontend: http://localhost:5173"
    echo "  API docs: http://localhost:8000/docs"
    echo "  Health:   http://localhost:8000/health"
    echo
    echo "Useful commands:"
    echo "  ./project.sh logs"
    echo "  ./project.sh status"
    echo "  ./project.sh stop"
}

command="${1:-start}"

case "${command}" in
    start)
        require_docker
        start_project
        ;;
    status)
        require_docker
        require_configuration
        docker compose ps -a
        ;;
    logs)
        require_docker
        require_configuration
        exec docker compose logs --follow --tail=100
        ;;
    demo-data)
        require_docker
        require_configuration
        if [[ "${DEMO_MODE:-}" != "1" ]]; then
            echo "Set DEMO_MODE=1 to enable synthetic demo seeding." >&2
            exit 2
        fi
        if [[ -z "${DEMO_PASSWORD:-}" ]]; then
            echo "Set DEMO_PASSWORD in the shell for this synthetic demo command." >&2
            exit 2
        fi
        docker compose exec -T -e DEMO_PASSWORD="${DEMO_PASSWORD}" api python -m scripts.seed_demo
        ;;
    stop)
        require_docker
        require_configuration
        docker compose stop
        echo "Project stopped. PostgreSQL data was preserved in the Docker volume."
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: ${command}" >&2
        usage >&2
        exit 2
        ;;
esac
