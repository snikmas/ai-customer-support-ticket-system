# ResolveAI — Code Review Findings

Full codebase review (2026-09-29). Backend test suite: 329 passed. Frontend: 12 tests passed, build clean. Migrations match models. The three critical bugs were verified empirically, not just by reading code.

**Resolution pass (2026-09-29):** all findings fixed and verified. Backend: 355 passed (26 new regression tests). Frontend: 18 passed, build clean. Ruff clean under widened `E4,E7,E9,F` rules. Two new migrations, single head.

## Critical bugs (verified)

### 1. `GET /jobs/` (admin job listing) crashes with 500 — ✅ FIXED
- `src/constants/helpers.py:184` — `raw_job_to_job_response` builds `models.jobs.Job` whose fields are all `str` (`result`, `created_at`, `enqueued_at`, `ended_at`). Real RQ jobs have `result=None`, `enqueued_at=None`, and `datetime` objects → pydantic `ValidationError` (confirmed by running it against a realistic job object).
- `src/routers/jobs.py:20` — additionally declares `-> list[JobStatusResponse]` while the service returns `Job` objects (`id`, not `job_id`), so FastAPI response validation would fail even if construction succeeded.
- `src/tests/test_jobs.py` never tests `get_all_jobs`, so the suite stays green while the endpoint is dead.
- **Fix:** `raw_job_to_job_response` now returns `JobStatusResponse` directly; router annotation matches the service. New tests cover the service and the HTTP endpoint.

### 2. Single-comment endpoint leaks comments to unrelated agents (IDOR) — ✅ FIXED
- `src/services/comments.py:86` — `get_comment` checks comment visibility but never whether an agent is assigned to the ticket / the ticket is in the NEW queue. `get_all_comments` (line 49) does check via `_check_agent_can_access_ticket`.
- Verified: an agent read an `INTERNAL` comment on an `IN_PROGRESS` ticket assigned to another agent.
- Contradicts `docs/PERMISSIONS.md` ("Agent: assigned/new queue").
- Fix: call `_check_agent_can_access_ticket(ticket, requester)` for `Role.AGENT` in `get_comment`.
- **Fix applied as specified** (`src/services/comments.py:104`), mirroring `get_all_comments` semantics. Regression tests for both deny (assigned to another agent) and allow (unassigned NEW) paths.

### 3. The last Super Admin can be deleted — ✅ FIXED
- `src/services/users.py:548` — `delete_user` has no `count_active_superadmins` / `LastSuperAdminError` guard, while `update_user` (lines 469–496) protects both last-super-admin and final-admin-access.
- Verified: an ADMIN deleted the only SUPER_ADMIN without error.
- Contradicts `docs/PERMISSIONS.md:19` ("The last active Super Admin ... protected by domain conflicts").
- **Fix:** `delete_user` now raises `LastSuperAdminError` / `FinalAdminAccessError` (`src/services/users.py:560`) and rejects non-super-admins managing super admins. Four new tests incl. admin-deleting-superadmin and self-delete.

## Smaller bugs and inconsistencies

- [x] **4. `get_job` IndexError on cron jobs** — `src/jobs/service.py:179` does `raw_job.args[0]` for jobs without `meta`. Cron-enqueued jobs (`route_waiting_tickets`, `scan_overdue_tickets`) take only kwargs → `IndexError` → 500 when querying their job ID. **Fixed:** `elif raw_job.args:` guard; cron-job regression test added.
- [x] **5. Misleading comment notification** — `src/services/comments.py:163` says "A new *visible* comment was added" but fires for every visibility, including `PRIVATE_TO_MANAGER`, which the notified agent cannot read. **Fixed:** notification skipped for `PRIVATE_TO_MANAGER`; tests for both notify/no-notify paths.
- [x] **6. Capacity bypass on manual assignment** — automatic routing enforces `max_active_tickets`/availability (`src/db/operations.py:622`), but `claim_ticket`, `assign_ticket`, and PATCH-assignment in `update_ticket` don't. Decide whether this is an intentional manual override; if yes, document it in `docs/TICKET_WORKFLOW.md`. **Resolved as documented decision:** `claim_ticket` now enforces availability/capacity (new `AgentUnavailableError`/`AgentAtCapacityError` 409s); manager/admin manual assignment is an intentional override, documented in `docs/TICKET_WORKFLOW.md`.
- [x] **7. Login rate-limit IP is constant behind nginx** — `src/routers/auth.py:37` uses `request.client.host`, but nginx proxies all traffic so the IP is always the nginx container's (uvicorn doesn't trust `X-Forwarded-For`, which `site/nginx.conf:14` sets). The identifier half of the key still works. **Fixed:** `_get_client_host` reads the rightmost `X-Forwarded-For` entry.
- [x] **8. No refresh-token reuse detection** — `src/services/auth.py:134` rotates atomically (good), but a stolen old token just gets "not found" instead of revoking the session family. **Fixed:** `previous_refresh_token_hash` column (+ migration `f00c00cb587a`); reuse of a rotated token revokes the whole session family.
- [x] **9. Timing-based user enumeration** — `src/services/auth.py:26` `login_user` returns immediately for unknown identifiers but runs argon2/bcrypt for existing ones. **Fixed:** dummy argon2 verification for unknown/inactive identifiers.
- [x] **10. Frontend stricter than backend** — `site/src/pages/TicketDetailPage.tsx:295` `canComment` denies agents commenting on unassigned NEW tickets, though the API allows it. **Fixed:** extracted `computeCanComment` matching the backend rule (NEW + unassigned allowed); unit-tested.

## Code quality

- [x] **11. Nullable typing nits** — `src/db/models.py`: `Ticket.tags` and `Ticket.deleted_at` are nullable columns typed `Mapped[str]` / `Mapped[datetime]` instead of `Optional[...]`. **Fixed.**
- [x] **12. Inconsistent datetime columns** — `User`/`AgentProfile` use plain `DateTime(timezone=True)`; everything else uses the strict `UTCDateTime` guard. **Fixed:** all use `UTCDateTime`.
- [x] **13. `Ticket.tags` is `String(200)` holding JSON** — current tag set fits (~140 chars worst case for 10 tags), but one longer tag in the enum will silently break inserts on PostgreSQL. Widen the column or enforce serialized length. **Fixed:** widened to `String(500)` + migration `4c417c90dada`; `render_as_batch=True` in `alembic/env.py` so ALTER works on SQLite.
- [x] **14. `inspect.signature` runtime shims** — `src/routers/tickets.py:39` and `src/services/tickets.py:393` probe their own collaborators' signatures to support "old unit-test doubles". Fix the test doubles instead of sniffing signatures in production code. **Fixed:** shims removed, direct calls; test doubles updated.
- [x] **15. Learning-log comments and typos** — `src/cache/rate_limit.py:25-34`, `src/core/security.py:1`, `src/services/users.py:269`, `src/constants/helpers.py:13`, "suppoer worker", "whcih", "STANDARTIZATION PROCESS", `created_refresh_section` typo in `src/routers/auth.py:53`. **Fixed:** all cleaned.
- [x] **16. Dead code** — `src/core/config.py:17-22` (`DEBUG`, `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MIN`); `TicketUpdate.deleted_at`; the whole `delete_all_users` path (service + operations); unused imports (`jobs_get_job`, `AuditLogError` in `src/services/tickets.py`). **Fixed:** all removed, incl. the `models.jobs.Job` model left unused after fix #1.
- [x] **17. Ruff only checks `E9`+`F821`** (`pyproject.toml:4`) — syntax errors and undefined names only. Widening to the default `E4,E7,E9,F` would catch the unused imports. **Fixed:** widened; `ruff check` clean.
- [x] **18. ORM mutation in `_to_api_ticket`** (`src/services/tickets.py:41`) — assigns a list onto the `tags` String column attribute of the ORM object. Harmless post-session, but dirty ORM state is a footgun. **Fixed:** builds a plain dict for `model_validate`, no ORM mutation.

## Environment

- [ ] **19.** Project `api` and `frontend` containers were not running during review (only db/redis/worker/cron up). Two foreign containers (`resolveai-review-ui/pg-limah0w3`) exist that are not from this `compose.yaml` — investigate before a demo. **Still open** — environmental, no code change.

## What's solid (interview talking points)

- Migrations match models exactly, incl. dialect-specific enum evolution and the partial unique index for active analyses.
- Concurrency handling: SQLite `BEGIN IMMEDIATE` vs PostgreSQL `FOR UPDATE` / `LOCK TABLE` in `try_route_ticket`, `create_initial_superadmin`, `record_overdue_ticket_events`.
- Analysis lifecycle: durable PENDING row, provenance snapshot before enqueue, bounded retries, safe error codes, DB check constraint enforcing the state machine (`src/db/models.py:419`).
- Attachments: extension/MIME agreement, read-limit size check, generated storage keys, Content-Disposition sanitization.
- Shared error envelope, honest provider privacy notices, deterministic fake analyzer as default.
