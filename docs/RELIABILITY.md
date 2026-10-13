# Reliability and security notes

- PostgreSQL migrations run before API/worker startup in Compose.
- `/health` reports database and Redis dependency state (liveness). It is not a
  worker-readiness signal. `/health/ready` separately requires a fresh worker
  heartbeat, worker subscriptions to every expected queue, and fresh
  scheduler/cron activity; a stack with a dead worker is `200` on `/health` but
  `503` on `/health/ready`. See [OPERATIONS.md](OPERATIONS.md).
- Redis is used for rate limiting, cache, and job dispatch. Ticket detail reads
  can fall back to SQL when the cache is unavailable; login throttling fails
  closed. Redis queue loss never loses work: SQL is the source of truth and the
  bounded analysis reconciler re-dispatches lost `Pending` rows and moves
  abandoned `Running` rows to a human-retry terminal state.
- Business writes and audit events share a SQL transaction where the existing
  operation supports it. RQ job IDs are not the durable analysis source of
  truth.
- AI setting updates use optimistic version checking and atomically record a
  provider/model audit event. Provider tests never mutate the active setting.
- Analysis rows snapshot provider/model/prompt provenance before enqueue. The
  worker never silently falls back after a provider failure; retryable errors
  use the existing bounded RQ lifecycle and permanent errors become safe
  durable failures.
- Provider keys remain process environment values. API responses, audit rows,
  logs, and verification evidence contain no credentials, prompts, outputs, or
  raw upstream error bodies. `src/core/logging.py` is the single logging owner;
  it redacts credentials, request/provider bodies, and database parameter
  values, and attaches request/ticket/analysis/job/attempt correlation IDs
  (proven with synthetic sentinels in `test_logging_redaction.py`).
- Real provider calls set an explicit output cap (`ANALYZER_MAX_OUTPUT_TOKENS`),
  and the automatic suite uses the fake provider only.
- Notification delivery is idempotent by key and best-effort after the primary
  ticket/comment write. The recipient-only read endpoints remain authoritative.
- Attachment storage keys are generated, path traversal is rejected, received
  byte length is checked, and user filenames are never used as filesystem
  paths. Comment/ticket authorization is repeated on download.
- Attachment uploads spool and validate before locking, enforce the five-file
  cap under a per-comment write lock, increment the counter atomically, and run
  blocking work off the async event loop. A failed metadata commit removes only
  the unreferenced generated blob. `scripts/cleanup_attachments.py` previews
  orphan blobs by default and never removes a referenced key.
- Compose `project.sh stop` preserves volumes. There is intentionally no reset
  command in the launcher.
- Every long-running Compose service uses `restart: unless-stopped`, so a Docker
  daemon restart does not leave the API running without PostgreSQL, Redis, or
  the frontend. The one-shot migration service intentionally does not restart.

Production follow-ups would add structured metrics/traces, external object
storage, a managed secret store, background orphan cleanup, and a service
manager/orchestrator with graceful rollout/readiness policy.

## Dependency audit boundary

Both `npm audit` and `npm audit --omit=dev` now report zero vulnerabilities
(`source-map-js` was upgraded to 1.2.2). The frontend lockfile change is scoped
to that single resolution. Python dependencies were audited with `pip-audit` in
a clean venv installed from pinned requirements: no known vulnerabilities
(`PyJWT` was upgraded to 2.15.0). CI runs the full frontend audit and an
advisory Python audit; public-hosting hardening (TLS, proxy trust, rate limits,
quotas, backups) is tracked as OPEN in [OPERATIONS.md](OPERATIONS.md).
