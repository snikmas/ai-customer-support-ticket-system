# Reliability and security notes

- PostgreSQL migrations run before API/worker startup in Compose.
- `/health` reports database and Redis dependency state; it is a readiness
  signal for this local stack, not a production SLO.
- Redis is used for rate limiting and cache. Ticket detail reads can fall back
  to SQL when the cache is unavailable; login throttling fails closed.
- Business writes and audit events share a SQL transaction where the existing
  operation supports it. RQ job IDs are not the durable analysis source of
  truth.
- Notification delivery is idempotent by key and best-effort after the primary
  ticket/comment write. The recipient-only read endpoints remain authoritative.
- Attachment storage keys are generated, path traversal is rejected, received
  byte length is checked, and user filenames are never used as filesystem
  paths. Comment/ticket authorization is repeated on download.
- Compose `project.sh stop` preserves volumes. There is intentionally no reset
  command in the launcher.

Production follow-ups would add structured metrics/traces, external object
storage, a managed secret store, background orphan cleanup, and a service
manager/orchestrator with graceful rollout/readiness policy.

## Dependency audit boundary

The production dependency check is `npm audit --omit=dev` and currently reports
zero vulnerabilities. A full audit reports one high and one moderate advisory
in the transitive development-only chain `vite -> postcss -> nanoid`; these
packages are not shipped in the nginx runtime image. The patched React Router
version remains in place. CI gates the production dependency set and records
this dev-tool risk until the upstream chain publishes a compatible fix.
