#!/usr/bin/env python
"""Full-stack HTTP smoke gate through nginx for the local Compose stack.

It builds and starts ``compose.smoke.yaml`` (a task-owned stack with synthetic
credentials, throwaway JWT keys, and high loopback ports), then drives the real
request path ``HTTP client -> nginx -> Uvicorn/FastAPI -> PostgreSQL/Redis``.

Checks:
1. A permitted attachment larger than 1 MiB is accepted through nginx.
2. Refresh-token rotation returns new tokens and rejects the used token.
3. Recreating the API container keeps nginx's upstream discovery working
   (Docker DNS re-resolution), verified through /api/health.

An oversized request is rejected by nginx before it reaches FastAPI.

Nothing here contacts a real provider or reads a developer ``.env``: the smoke
compose file pins the fake analyzer and synthetic secrets. The script requires a
working Docker daemon and always recreates the stack from a clean state, then
tears it down (``down -v``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "compose.smoke.yaml"
KEYS_DIR = REPO_ROOT / "scripts" / "nginx_smoke" / "keys"
PROJECT_NAME = "resolveai-smoke"

DEFAULT_WEB_PORT = 18080
STARTUP_TIMEOUT_SECONDS = 300.0
RECREATE_TIMEOUT_SECONDS = 90.0

PERMITTED_UPLOAD_BYTES = 2 * 1024 * 1024  # > 1 MiB, < 5 MiB app limit
OVERSIZED_UPLOAD_BYTES = 7 * 1024 * 1024  # > nginx 6 MiB client_max_body_size


class SmokeFailure(AssertionError):
    pass


def _run(command: list[str], *, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )


def _compose(env: dict[str, str], *args: str, timeout: float = 900.0) -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], env=env, timeout=timeout)


def _generate_keys() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (KEYS_DIR / "private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (KEYS_DIR / "public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    # The API container runs as an unprivileged user, so the mounted throwaway
    # keys must be world-readable. They are disposable and never reused.
    for name in ("private.pem", "public.pem"):
        os.chmod(KEYS_DIR / name, 0o644)


def _base_url(web_port: int) -> str:
    return f"http://127.0.0.1:{web_port}"


def _wait_for_health(client, web_port: int, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{_base_url(web_port)}/api/health", timeout=5.0)
            last = f"HTTP {response.status_code}"
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 - retry until the deadline
            last = repr(exc)
        time.sleep(1.0)
    raise SmokeFailure(f"nginx/API never became healthy (last: {last})")


def _register_login(client, base: str, credentials: dict[str, str]) -> dict[str, str]:
    created = client.post(f"{base}/api/users/", json=credentials)
    if created.status_code != 201:
        raise SmokeFailure(f"user registration failed: {created.status_code} {created.text[:200]}")
    login = client.post(
        f"{base}/api/auth/login",
        json={"nickname": credentials["nickname"], "password": credentials["password"]},
    )
    if login.status_code != 200:
        raise SmokeFailure(f"login failed: {login.status_code} {login.text[:200]}")
    return login.json()


def _create_comment(client, base: str, token: str, ticket_id: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    comment = client.post(
        f"{base}/api/tickets/{ticket_id}/comments",
        json={"body": "Synthetic smoke comment.", "visibility": "Public"},
        headers=headers,
    )
    if comment.status_code != 201:
        raise SmokeFailure(f"comment creation failed: {comment.status_code} {comment.text[:200]}")
    return comment.json()["data"]["id"]


def check_permitted_upload(client, base: str, token: str, ticket_id: str, comment_id: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"a" * PERMITTED_UPLOAD_BYTES
    response = client.post(
        f"{base}/api/tickets/{ticket_id}/comments/{comment_id}/attachments",
        files={"file": ("permitted-sample.txt", payload, "text/plain")},
        headers=headers,
        timeout=60.0,
    )
    if response.status_code != 201:
        raise SmokeFailure(
            f"permitted {PERMITTED_UPLOAD_BYTES} byte upload failed: "
            f"{response.status_code} {response.text[:200]}"
        )
    size = response.json()["data"]["size_bytes"]
    if size != PERMITTED_UPLOAD_BYTES:
        raise SmokeFailure(f"stored attachment size {size} != {PERMITTED_UPLOAD_BYTES}")
    print(f"PASS permitted upload: {size} bytes accepted through nginx (> 1 MiB)")


def check_oversized_rejected(client, base: str, token: str, ticket_id: str, comment_id: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"a" * OVERSIZED_UPLOAD_BYTES
    response = client.post(
        f"{base}/api/tickets/{ticket_id}/comments/{comment_id}/attachments",
        files={"file": ("oversized-sample.txt", payload, "text/plain")},
        headers=headers,
        timeout=60.0,
    )
    if response.status_code != 413:
        raise SmokeFailure(
            f"oversized upload should be rejected by nginx with 413, got "
            f"{response.status_code} {response.text[:200]}"
        )
    print(f"PASS oversized upload rejected: {response.status_code} from nginx")


def check_token_refresh(client, base: str, initial: dict[str, str]) -> None:
    old_refresh = initial["refresh_token"]
    refreshed = client.post(f"{base}/api/auth/refresh", json={"refresh_token": old_refresh})
    if refreshed.status_code != 200:
        raise SmokeFailure(f"refresh failed: {refreshed.status_code} {refreshed.text[:200]}")
    new_tokens = refreshed.json()
    if not new_tokens.get("access_token") or not new_tokens.get("refresh_token"):
        raise SmokeFailure("refresh response is missing tokens")
    if new_tokens["refresh_token"] == old_refresh:
        raise SmokeFailure("refresh did not rotate the refresh token")

    reused = client.post(f"{base}/api/auth/refresh", json={"refresh_token": old_refresh})
    if reused.status_code != 401:
        raise SmokeFailure(
            f"reusing a rotated refresh token should return 401, got {reused.status_code}"
        )

    listed = client.get(
        f"{base}/api/tickets/",
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    if listed.status_code != 200:
        raise SmokeFailure(f"new access token rejected: {listed.status_code}")
    print("PASS token refresh: rotation returned new tokens and 401 for the used token")


def _wait_for_readiness(client, base: str, *, expect_ready: bool, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"{base}/api/health/ready", timeout=5.0)
        try:
            body = response.json()
        except Exception:  # noqa: BLE001 - non-JSON body is a failure detail
            body = {"status": "unparseable"}
        last = (response.status_code, body)
        if expect_ready and response.status_code == 200 and body.get("ready") is True:
            return body
        if not expect_ready and response.status_code == 503 and body.get("ready") is False:
            return body
        time.sleep(1.0)
    raise SmokeFailure(f"readiness never reached expected state (last: {last})")


def check_readiness_stack(client, env: dict[str, str], base: str) -> None:
    """Prove /health/ready goes green, red for a missing component, then green.

    A fresh worker/scheduler/cron must report ready; stopping the background
    services must produce a documented not-ready report while ordinary API
    health stays up; restarting them must recover readiness.
    """
    ready = _wait_for_readiness(
        client, base, expect_ready=True, timeout=STARTUP_TIMEOUT_SECONDS
    )
    checks = ready["checks"]
    for name in (
        "database",
        "redis",
        "worker_heartbeat",
        "queue_subscriptions",
        "scheduler_heartbeat",
        "cron_registry",
    ):
        if not checks[name]["ok"]:
            raise SmokeFailure(f"ready report has {name} not ok: {checks[name]}")
    print("PASS readiness: worker, scheduler, queue subscriptions, and cron all fresh")

    # Stop the background components. The API and its data stores stay healthy,
    # so /health must remain 200 while background readiness reports the gap.
    stopped = _compose(env, "stop", "worker", "cron", timeout=120.0)
    if stopped.returncode != 0:
        raise SmokeFailure(f"stopping background services failed:\n{stopped.stdout[-1000:]}")

    degraded = _wait_for_readiness(
        client, base, expect_ready=False, timeout=RECREATE_TIMEOUT_SECONDS
    )
    for name in ("worker_heartbeat", "scheduler_heartbeat"):
        if degraded["checks"][name]["ok"]:
            raise SmokeFailure(f"stopped worker still reports {name} ok")
    if not degraded["checks"]["database"]["ok"]:
        raise SmokeFailure("database must stay healthy while only workers are down")
    health = client.get(f"{base}/api/health", timeout=5.0)
    if health.status_code != 200:
        raise SmokeFailure(
            f"API health must stay 200 while background work is down, got {health.status_code}"
        )
    print("PASS readiness: missing worker/scheduler reported while /health stays up")

    restarted = _compose(env, "start", "worker", "cron", timeout=120.0)
    if restarted.returncode != 0:
        raise SmokeFailure(f"restarting background services failed:\n{restarted.stdout[-1000:]}")
    _wait_for_readiness(client, base, expect_ready=True, timeout=RECREATE_TIMEOUT_SECONDS)
    print("PASS readiness: recovered after the background services restarted")


def check_recreated_api_discovery(client, env: dict[str, str], web_port: int) -> None:
    before = client.get(f"{_base_url(web_port)}/api/health", timeout=5.0)
    if before.status_code != 200:
        raise SmokeFailure(f"health before recreation was {before.status_code}")

    recreated = _compose(env, "up", "-d", "--force-recreate", "api", timeout=300.0)
    if recreated.returncode != 0:
        raise SmokeFailure(f"api recreation failed:\n{recreated.stdout[-1000:]}")

    # Docker assigns the recreated container a new IP. nginx only recovers
    # because its upstream uses Docker's embedded DNS with a short valid= TTL.
    _wait_for_health(client, web_port, timeout=RECREATE_TIMEOUT_SECONDS)
    after = client.get(f"{_base_url(web_port)}/api/health", timeout=5.0)
    if after.status_code != 200:
        raise SmokeFailure(f"health after recreation was {after.status_code}")
    print("PASS recreated API discovery: nginx kept proxying after api restart")


def _run_checks(client, env: dict[str, str], web_port: int) -> None:
    base = _base_url(web_port)
    # Recreate from a clean state so a previous failed run cannot mask issues.
    _compose(env, "down", "-v", "--remove-orphans", timeout=300.0)
    started = _compose(env, "up", "-d", "--build", timeout=1800.0)
    if started.returncode != 0:
        raise SmokeFailure(f"docker compose up failed:\n{started.stdout[-2000:]}")
    _wait_for_health(client, web_port, timeout=STARTUP_TIMEOUT_SECONDS)
    check_readiness_stack(client, env, base)

    credentials = {
        "nickname": "smokeuser",
        "first_name": "Smoke",
        "last_name": "User",
        "password": "smoke-password-1234567890",
        "phone": "+15550001234",
        "email": "smokeuser@example.com",
    }
    tokens = _register_login(client, base, credentials)

    ticket = client.post(
        f"{base}/api/tickets/",
        json={
            "title": "Smoke upload ticket",
            "description": "Synthetic ticket created by the Phase I smoke gate.",
            "category": "API_Error",
            "tags": [],
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    if ticket.status_code != 201:
        raise SmokeFailure(f"ticket creation failed: {ticket.status_code} {ticket.text[:200]}")
    ticket_id = ticket.json()["data"]["id"]
    comment_id = _create_comment(client, base, tokens["access_token"], ticket_id)

    check_permitted_upload(client, base, tokens["access_token"], ticket_id, comment_id)
    check_oversized_rejected(client, base, tokens["access_token"], ticket_id, comment_id)
    check_token_refresh(client, base, tokens)
    check_recreated_api_discovery(client, env, web_port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--web-port",
        type=int,
        default=int(os.getenv("SMOKE_WEB_PORT", DEFAULT_WEB_PORT)),
    )
    parser.add_argument(
        "--keep-stack",
        action="store_true",
        help="Leave the smoke stack running for debugging.",
    )
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])

    if shutil.which("docker") is None:
        raise SystemExit("docker is not installed; cannot run the nginx smoke gate")

    import httpx

    env = os.environ.copy()
    env["SMOKE_WEB_PORT"] = str(args.web_port)

    _generate_keys()
    try:
        # trust_env=False keeps a developer's HTTP(S)/SOCKS proxy settings out
        # of a loopback smoke test.
        with httpx.Client(http2=False, follow_redirects=False, trust_env=False) as client:
            _run_checks(client, env, args.web_port)
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        if not args.keep_stack:
            logs = _compose(env, "logs", "--no-color", "--tail", "50", timeout=120.0)
            print(logs.stdout[-4000:], file=sys.stderr)
        return 1
    finally:
        if not args.keep_stack:
            _compose(env, "down", "-v", "--remove-orphans", timeout=300.0)
    print("All nginx HTTP smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
