# Architecture

ResolveAI is a local staff ticket workspace. The browser calls FastAPI with a
Bearer access token. FastAPI dependencies authenticate the token, services
apply domain permissions, and SQLAlchemy operations own database transactions.

```text
React/Vite browser
       |
       | HTTP + Bearer JWT
       v
FastAPI routers -> auth dependency -> services -> SQLAlchemy -> PostgreSQL
       |                                      |                 |
       |                                      +-> Redis cache/rate limits
       +-> RQ enqueue -> Redis queue -> worker -> durable SQL result
```

Synchronous ticket, user, comment, routing-catalog, customer-summary,
attachment, related-link, and notification requests use the first path.
Routing and AI analysis cross a process boundary through Redis/RQ; the durable
database record is the source of truth when a worker is delayed or restarted.

## Provider selection and provenance

The `ai_settings` table contains exactly one global provider/model selection,
seeded to the deterministic fake provider. Admin and Super Admin updates use an
optimistic version and write a safe audit event in the same transaction. The
API exposes readiness and privacy notices, never credentials.

When an analysis is reserved, `AnalysisResult` stores the provider, model, and
prompt version before the RQ enqueue. The worker builds an adapter from that
immutable row, not from the latest global setting. A later administrator change
therefore affects new analyses without rewriting queued work.

Supported adapters are the local fake analyzer, OpenRouter with its existing
structured-output and data-collection controls, and direct DeepSeek at the
fixed official endpoint. Each adapter owns its payload shape, response
validation, token accounting, and safe error mapping. The fake adapter is the
verified local-demo provider. Real-provider (OpenRouter/DeepSeek) output quality
is **unverified**: no authorized, budgeted evaluation of a real model is part of
this release, and the automated suite never calls a paid provider. See
[AI_EVALUATION.md](AI_EVALUATION.md).

## Request walkthroughs

**Synchronous request — `GET /tickets/{ticket_id}`.** The browser sends an HTTP
request with a Bearer access token. A FastAPI router calls the auth dependency,
which verifies the JWT and loads the caller. The service layer checks that the
caller may read this ticket (owner, assigned/NEW agent, read-only, or manager)
before touching SQL. `src/db/operations` reads the ticket through SQLAlchemy,
using the Redis ticket-detail cache when present and falling back to SQL on a
cache miss or Redis failure. The router serializes the SQLAlchemy row into the
Pydantic response model and returns JSON. No background process is involved, so
a Redis outage degrades this path to a slower SQL read rather than a failure.

**Background request — AI analysis.** The API first *reserves* work by writing a
durable `PENDING` `AnalysisResult` row that snapshots the ticket input and the
provider/model/prompt provenance. Only then does it enqueue the stable RQ job
`analyze-result-<id>` on the `ticket_jobs` queue. An RQ worker claims the row
under a lease, runs the snapshot's adapter (fake by default), and stores
`COMPLETED` or `FAILED` back on the same row. The browser polls the row, not the
RQ job. SQL is the source of truth: if Redis or the worker is lost after the
reservation, the bounded reconciler re-dispatches clearly-unstarted work and
moves an interrupted provider call to the safe terminal
`provider_result_unknown` state for a human retry.

Local attachments use `LocalAttachmentStorage` and the Compose `attachments`
volume. The adapter has one small interface so a production deployment can
replace it with S3-compatible object storage without exposing filenames as
paths. Attachments are never included in the AI analyzer snapshot.

PostgreSQL schema changes are owned by Alembic. SQLite remains useful for unit
tests and quick local runs; the Stage 10 migration is dialect-compatible.
