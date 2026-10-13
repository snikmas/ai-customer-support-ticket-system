# Interview code and runtime check

**30 September 2026 · repository baseline `0f95921` plus the local changes from this review**

## Assessment

The reviewed checkout builds and passes the checks below. The normal Docker application has been rebuilt with the fixes. Ordinary ticket handling and the local fake analysis workflow were exercised against real PostgreSQL, Redis, RQ, and Nginx, and through the browser.

This is an interview rehearsal and code audit. It does not establish absence of all bugs or production readiness. The most important remaining technical risk is analysis recovery after hard worker termination. Real external-provider availability and Mary's own demo account are separate checks.

## Scope

Reviewed the application entrypoint, request models, ORM relationships and constraints, authentication, permissions, ticket/comment/user services, SQL operations, cache/limits, worker tasks and scheduling, provider adapters, file storage, frontend pages/client/authentication, migrations, container setup, launcher, existing tests, CI, and existing documentation.

The review followed request and job paths, including alternate endpoints and direct resource access. Generated dependency directories and archived examples were not treated as application source. Secret files, key contents, tokens, and credential values were not inspected. Runtime exercises used isolated synthetic data and in-memory generated signing keys. The ordinary application used its existing runtime configuration during container startup.

## Verification evidence

| Check | Result | Evidence / practical limit |
|---|---|---|
| Backend baseline | 356 tests passed before fixes. | Demonstrates why green baseline tests did not cover all runtime defects. |
| Final backend | **379 passed**. | `PYTHON_DOTENV_DISABLED=1 REDIS_ENABLED=false ANALYZER_PROVIDER=fake myvenv/bin/python -m pytest -q` |
| Ruff | Passed. | `myvenv/bin/ruff check main.py src scripts bootstrap_superadmin.py` |
| Frontend | **19 passed**, four files. | `cd site; npm test` |
| TypeScript | Passed. | `cd site; npm run lint` |
| Production frontend build | Passed in Docker, including `npm ci` and `npm run build`. | Secret frontend configuration excluded from build context. |
| Dependency audit | **0 known npm vulnerabilities** at check time. | Full `npm audit`; initial audit found three moderate and one high development dependency advisories. |
| Fresh PostgreSQL migrations | All revisions applied successfully. | Disposable PostgreSQL 16, migration head `4c417c90dada`. |
| Main HTTP journey | **56/56 checks passed**. | [Recorded statuses](audit/2026-09-30/http-journey.json) |
| Additional adversarial journey | **11/11 checks passed**. | [Recorded checks](audit/2026-09-30/adversarial-journey.json) |
| PostgreSQL automatic-routing race | One assignment, one no-eligible-agent result; capacity one, workload one. | Before fix: both assigned, workload two. [Recorded final outcomes](audit/2026-09-30/postgres-capacity.json), distinct tickets and concurrent transactions. |
| PostgreSQL claim race | One claimed, one capacity conflict; workload one. | Claim repeats eligibility/capacity checks under the write transaction. |
| Retry failure | Three attempts, final Failed, `provider_unavailable`. | [Retry evidence](audit/2026-09-30/retry.json); real worker/scheduler, deliberately failing fake adapter. |
| Cached access after reassignment | Previous agent gets 403; current agent gets 200. | [Cache evidence](audit/2026-09-30/cache-access.json); SQL changed without cache invalidation intentionally. |
| Proxy DNS change | Backend moved to a different container IP; proxy recovered without frontend restart. | [DNS evidence](audit/2026-09-30/proxy-dns.json) |
| Normal launcher | `./project.sh` exited 0 after final rebuild. | Existing runtime configuration and administrator preserved; private values not inspected. |
| Normal Docker deployment | API and proxy health return 200 with SQL/Redis up. Worker registered and consumes operational work. Migration exited 0. | Checked after rebuilding. Health is not provider/worker/business acceptance. |
| Browser | Login, pages, creation, reply/file upload, download, analysis, transitions, availability reasons, role-specific controls. | Synthetic admin, agent, and customer sessions. Screenshots below. |
| Responsive rendering | Inspected mobile, tablet, desktop ticket views. | Waited for sidebar CSS transition before final captures. |

The main journey covers customer/staff access, triage, automatic assignment, Start work and repeated-action conflict, public/internal/private notes, direct hidden-note access, customer summaries, a small and 2 MiB attachment through Nginx, exact download bytes, real fake analysis completion, job status, notifications, resolution/closure/reopening, AI settings testing/version conflict, null updates, and cross-department assignment rejection.

The additional journey checks refresh rotation/replay/revocation, related links/duplicates/self-links, historical note redaction after publication, file-size/type rejection, and the documented continued validity of an existing access JWT after refresh-session revocation.

## Defects reproduced and fixed

| Finding | Why it mattered | Narrow correction | Regression evidence |
|---|---|---|---|
| Explicit null updates reached mandatory SQL fields or enum calculations. | Ordinary invalid input produced 500 or inconsistent responses. | Reject null for mandatory update fields; allow omission and intentional nullable fields. | Parameterized schema tests and real 422 responses. |
| Validation response included raw input. | Invalid password input could be echoed. | Remove `input` and exception `ctx` from validation details. | Password-echo regression. |
| Generic assignment PATCH bypassed department validation. | Alternate route violated routing ownership rules. | Enforce active agent and active same-department validation. | Domain regression and HTTP 400. |
| Admin could modify/promote the highest role through broader update logic. | Administrative privilege boundary was inconsistent. | Require Super Admin authority for these operations. | Explicit denial tests. |
| Unique profile-field updates surfaced database errors. | Duplicate nickname/email/phone changes could produce 500. | Map uniqueness failure to a domain conflict. | IntegrityError regression. |
| Concurrent automatic routing used an old workload count after waiting for a lock. | Agent capacity could be exceeded. | Acquire department lock before the workload query starts. | [PostgreSQL capacity evidence](audit/2026-09-30/postgres-capacity.json). |
| Claim capacity was checked outside the write transaction. | Different tickets could be claimed concurrently beyond capacity. | Lock and recheck eligibility/workload during the claim transaction. | Database regression and real PostgreSQL race. |
| Priority sort depended on enum representation. | “Most urgent first” could show Normal/Low first. | Explicit SQL numeric priority ranking. | `[4, 3, 2, 1]` regression. |
| Cached assignment could authorize the previous agent. | Failed invalidation could preserve stale access. | Fresh SQL authorization projection on cache hits. | Red/green test and live stale-cache probe. |
| Historical note bodies followed current comment visibility. | Publishing a replacement could expose the old internal body. | Snapshot visibility on edits; redact historical bodies according to that snapshot. | Database regression and live history check. |
| Read-only agents could upload. | Read access incorrectly allowed a write. | Reject read-only upload requests. | Upload denial regression. |
| Malformed cached JSON caused an error. | Cache corruption could break otherwise readable tickets. | Treat decode/schema failure as a miss. | Malformed payload regression. |
| Nginx rejected valid attachment sizes. | Default 1 MiB body cap broke the API's 5 MiB contract. | 6 MiB API body cap for multipart overhead. | 2 MiB through-proxy upload and over-limit rejection. |
| Nginx retained a recreated API's old IP. | Frontend 502 while direct API health was 200. | Docker DNS resolver and dynamic upstream address resolution. | Disposable IP-change test without frontend restart. |
| Worker lacked delayed-job scheduler. | Interval retries could remain scheduled without execution. | `--with-scheduler` in Compose/local worker command. | Controlled three-attempt failure. |
| Download did not refresh expired access tokens. | Files could fail after 15 minutes even when refresh remained valid. | Refresh once, retry once. | New frontend test. |
| Availability reason was arbitrary text. | UI values such as “Break” did not match API enum `BREAK`. | Enumerated reason selector. | Browser saved Paused/Break successfully. |
| Frontend dependency advisories remained. | Development tooling had known vulnerable versions. | Update compatible lockfile resolutions. | Full audit zero; clean Docker build and tests. |

The changes add 23 backend regression cases and one frontend case. Two existing test fixtures were updated to satisfy the newly enforced department checks; those fixtures still test their original behavior.

## Browser evidence

All screenshots use disposable synthetic data.

- [Agent ticket](audit/2026-09-30/agent-ticket.png): completed fake summary, comments/files, permitted actions.
- [Customer ticket](audit/2026-09-30/customer-ticket.png): restricted customer controls; customer-summary panel is not available to that role.
- [Mobile ticket](audit/2026-09-30/ticket-mobile.png), [tablet ticket](audit/2026-09-30/ticket-tablet.png), [desktop ticket](audit/2026-09-30/ticket-desktop.png).

Expected authorization errors and brief outages during deliberate process restarts appeared in browser diagnostics. A fresh customer panel check had no console errors. This is not a claim that every possible browser action was exhaustively tested.

## Remaining findings and limits

| Priority | Finding | Effect / suggested next work |
|---|---|---|
| High | Hard worker termination can leave a durable analysis Running. | No complete stale-analysis reconciliation. Active-row deduplication can block a new request for that ticket. Add recovery that distinguishes live/retrying work from abandoned execution. |
| High | SQL reservation and Redis enqueue are separate operations. | A crash between reservation/enqueue/job-link persistence can leave inconsistent execution state. Add outbox/reconciliation rather than assuming atomicity across systems. |
| Medium | Some generic workflow/admin invariant checks occur before the final write. | Concurrent updates deserve more guarded transitions, including last-Super-Admin protection and complete agent role lifecycle. Existing tests do not establish all such races. |
| Medium | Agent promotion paths are not uniformly profile-aware. | User-to-Agent has special handling; other role changes can leave an Agent without the expected profile. Prefer preconfigured staff creation for the interview. |
| Medium | Redis queue persistence is not configured. | Redis loss can strand SQL analysis rows and remove queued work. SQL durability alone does not restore jobs. |
| Medium | Upload permission/count guarantees are incomplete beyond the read-only fix. | Upload permission remains mainly based on readable ticket/comment. The five-file check can race. A future write policy and transactional count reservation need explicit design. |
| Medium | Browser token/session limitations. | JavaScript can read sessionStorage tokens; logout does not immediately revoke every access JWT. Profile/role controls can be stale until session identity reloads. |
| Medium | Proxy attribution requires deployment configuration. | Untrusted raw headers no longer alter the limiter identity, but users behind a Docker proxy may share its effective address unless trusted peers are configured. |
| Medium | Optional frontend failures and bounded controls. | Empty panels can hide failed optional fetches. Staff directory and agent selectors have size limits; full agent profile editing remains API-only. |
| Medium | File storage and inspection. | Local bytes and SQL metadata lack a shared transaction; no malware scanning, content verification, retention, or storage quota system. |
| Medium | Operational exposure and logging. | Host ports bind all interfaces; no HTTPS in local Compose. Exception logs can include SQL parameters. No complete metrics/alerting/backup drill. |
| Low | Cached presentation can remain stale. | Authorization now reads fresh SQL. Presentation may still lag after failed invalidation until the 300-second TTL expires. |
| Unverified | Real OpenRouter/DeepSeek connectivity, cost, model output quality. | No paid calls or credential inspection. Mary should use Test provider with authorized synthetic content before claiming live external integration. |
| Pending human rehearsal | Mary's ordinary demo login and explanation. | Synthetic sessions prove the workflow, not that Mary has rehearsed her existing account or can explain it yet. |

## Changes to the running application

The ordinary API was initially stopped while the frontend was running. It was started, then API/worker/cron/frontend images were rebuilt and relevant containers recreated with the fixes. PostgreSQL and attachment volumes were preserved. No normal database reset or volume deletion was performed.

Only task-owned disposable processes/containers were used for intentional failures. Those services were stopped after collecting evidence, without deleting database volumes. Their data does not become interview demo data in the normal database. The normal application remains running.

## Reproduce the ordinary checks

Run from the repository root:

```bash
PYTHON_DOTENV_DISABLED=1 REDIS_ENABLED=false ANALYZER_PROVIDER=fake myvenv/bin/python -m pytest -q
myvenv/bin/ruff check main.py src scripts bootstrap_superadmin.py
```

From `site/`, run:

```bash
npm test
npm run lint
npm audit
```

For the production image, run `docker build -t resolveai-frontend-check ./site` from the repository root. For safe runtime evidence, use [the demo runbook](INTERVIEW_DEMO.md). Do not export private configuration or token values while collecting evidence.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for how these checks map to the code paths.
