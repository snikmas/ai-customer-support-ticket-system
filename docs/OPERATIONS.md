# Operations guide (local demo)

This document covers the operational boundaries that the interview demo relies
on. It is written against the repaired backend. Anything marked **OPEN** is a
public-hosting gate that is deliberately not implemented here.

## 1. Liveness vs readiness

There are two health endpoints, and they mean different things:

| Endpoint | Question it answers | Depends on |
| --- | --- | --- |
| `GET /health` | Is the API process alive and are its data stores reachable? | database, Redis (when enabled) |
| `GET /health/ready` | Can the system actually process background work? | database, Redis, **fresh worker heartbeat**, **queue subscriptions**, **fresh scheduler**, **fresh cron registry** |

`/health` returning `200` does **not** mean analysis or routing jobs are being
processed. A stack with a dead worker still returns `200` on `/health`.

`/health/ready` returns `503` with a per-check `checks` map. The worker checks
are evaluated by `src/jobs/readiness.py`:

- `worker_heartbeat` — at least one worker heartbeat newer than 60s.
- `queue_subscriptions` — a fresh worker subscribes to **every** expected queue
  (`WORKER_QUEUE_ORDER`: `ticket_jobs`, `ticket_routing`).
- `scheduler_heartbeat` — a `--with-scheduler` worker or the `rq cron` service
  has a heartbeat newer than 90s.
- `cron_registry` — the `rq:cron_schedulers` registry has a fresh entry (180s).

Example:

```bash
curl -s http://127.0.0.1:8000/health/ready | python -m json.tool
```

Production teams wire readiness to the load balancer / orchestrator (only route
traffic when ready) and alert on worker heartbeats separately from API 5xx rate.

## 2. Redis persistence and queue-loss behavior

Redis is a **dispatch mechanism, not the source of truth**. Durable state lives
in SQL:

- Analysis work is a durable `analysis_result` row (with execution ownership and
  a lease, added in the reliability repair).
- Routing work is derived from ticket rows via the fairness scan.

Durability choices for the local demo:

- The `redis` compose service runs with `--appendonly yes` so queued work
  survives a Redis restart in most cases.
- That durability is **best-effort**. Redis AOF can still lose the last writes,
  and losing Redis entirely must not lose work.

Recovery path when Redis data is lost: the bounded **reconciler** re-dispatches
`Pending` analysis rows whose job was never created or was lost, and moves
`Running` rows with an expired lease to a safe terminal state
(`provider_result_unknown`) that requires a human retry rather than silently
repeating a possibly billed provider call. See `docs/RELIABILITY.md` and the
Phase E tests (`src/tests/test_analysis_recovery.py`). Do **not** assume SQL
alone recreates jobs; the reconciler is what closes that gap.

## 3. Structured logging and redaction

`src/core/logging.py` is the single logging configuration owner. It:

- attaches a correlation context: `request`, `ticket`, `analysis`, `job`,
  `attempt` IDs, injected from `ContextVar`s so a request handler or worker task
  sets them once;
- redacts credentials, `password=`/`token=`/`api_key=` values, bearer tokens,
  JWTs, and sensitive `extra` fields (request bodies, provider bodies, DB
  parameter values) before any line is emitted.

Evidence: `src/tests/test_logging_redaction.py` proves a synthetic sentinel is
absent from rendered output. Production defaults keep `DATABASE_ECHO=false` so
SQL parameters are never logged.

## 4. Provider output limits and test budget

- Real provider calls set an explicit output cap
  (`ANALYZER_MAX_OUTPUT_TOKENS`, default 400) so a single analysis cannot run up
  an unbounded bill. See `src/analyzers/{deepseek,openrouter}.py`.
- Automated tests use the **fake** provider only
  (`ANALYZER_PROVIDER=fake`), which makes no network calls.
- Aggregate budget for a local run: at most 5 analysis requests per user per
  60s (`ANALYSIS_RATE_LIMIT_*`), each capped at 400 output tokens, with a
  provider retry budget of 2 retries and a bounded reconciliation batch. Real
  provider verification is a separate, explicit, manual step
  (`README` "Use the direct DeepSeek API") and is never part of the automatic
  suite.

## 5. Published ports

Compose publishes demo ports on **loopback only** (`127.0.0.1:8000`,
`127.0.0.1:5173`). Nothing is reachable from other hosts until the public
hosting gates below pass.

## 6. Public-hosting gates — OPEN

These are not implemented and must not be described as done:

- **TLS termination and trusted proxy peers.** Trust `Forwarded`/`X-Forwarded-For`
  only from configured proxies; do not trust client-supplied headers.
- **Direct API path.** The published API port can currently bypass nginx edge
  request-size/abuse controls; close or protect it before exposure.
- **Abuse limits.** Bound registration, login, uploads, and billable
  provider-test traffic (account/IP/global), and test Redis-failure behavior.
- **Storage quotas and retention.** Decide quota, retention, and whether
  file-content inspection / malware scanning is required.
- **Backup and restore.** Test restoration with disposable copies and define
  what happens to DB records, attachment bytes, and queued work.
- **Worker/queue failure alerts and an incident runbook.**
