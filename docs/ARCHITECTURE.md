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

Local attachments use `LocalAttachmentStorage` and the Compose `attachments`
volume. The adapter has one small interface so a production deployment can
replace it with S3-compatible object storage without exposing filenames as
paths. Attachments are never included in the AI analyzer snapshot.

PostgreSQL schema changes are owned by Alembic. SQLite remains useful for unit
tests and quick local runs; the Stage 10 migration is dialect-compatible.
