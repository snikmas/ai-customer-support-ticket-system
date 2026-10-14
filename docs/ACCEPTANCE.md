# Final v1 acceptance evidence

> **Historical document.** The automated numbers recorded on 2026-08-24 for the
> provider-selection closure are kept below for provenance and are **not**
> current.
>
> Local verification on 2026-10-14 (working tree on `b2b147b`):
> backend **544 passed / 44 skipped** on SQLite with dotenv disabled and Redis
> off. Before the packaging regression was added, the application suite recorded
> **586 passed / 0 skipped** with a task-owned PostgreSQL 16 target
> (`TEST_POSTGRES_URL` + `TEST_POSTGRES_ALLOW_DESTRUCTIVE=1`), frontend **51
> passed (12 files)**, Ruff, Python compilation, TypeScript and the production
> build clean, and `scripts/verify_release.py --compose` reporting PASS for all
> eight checks. The full-stack nginx smoke reports healthy readiness, readiness
> recovery after a real worker stop, a permitted upload above 1 MiB, an
> oversized 413, refresh-token rotation, and API discovery after the API
> container is recreated.
>
> The 44 SQLite skips are all opt-in integration cases: the PostgreSQL-parameter
> tests plus the Redis/RQ and provider-opt-in cases. They are skipped by design
> when no task-owned target is supplied; the PostgreSQL 16 run above executes
> them (0 skipped). Evidence is classified by type: **fake-provider**
> (automatic tests), **real-provider** (manual, synthetic only, and **not
> included** in this release), and **human demo** (browser journeys).

The final packaging check found that the archive omitted the documented
`project.sh` launcher. The allowlist now includes that executable launcher,
the frontend setup template, and the frontend README. A regression verifies
the archived launcher, its manifest entry, executable permissions, and
`--help` behavior without reading configuration or starting services. Archive
members are unique. A live routing check also verified that an assignable
ticket behind five blocked tickets was reached within three batches of two,
with fresh scanner and worker processes, a new arrival, and mixed fake analysis
work. This check used disposable SQLite and Redis; the earlier PostgreSQL suite
covers database concurrency.

Migration verification now launches Alembic through the active Python
interpreter. It works in an installed environment without a repository-local
`myvenv` directory. A regression exercises that environment boundary, and the
empty and populated PostgreSQL 16 migration paths passed on a fresh disposable
server after the change.

Recorded locally on 2026-08-24 during the ResolveAI provider-selection closure.
The sections below are historical Compose/browser evidence, not the current
release gate. See `docs/OPERATIONS.md` for current operations evidence.

## Automated checks

| Check | Result |
| --- | --- |
| `REDIS_ENABLED=false myvenv/bin/python -m pytest -q` | 329 passed |
| `cd site && npm test -- --run` | 4 files, 12 tests passed |
| `cd site && npm run build` | passed |
| `cd site && npm audit --omit=dev` | 0 vulnerabilities |
| `myvenv/bin/ruff check main.py src scripts bootstrap_superadmin.py` | passed (`E9`, `F821`) |
| `docker compose config --quiet` | passed |
| `python -m compileall ...`, `bash -n project.sh`, `git diff --check` | passed |
| `myvenv/bin/python scripts/verify_release.py` | passed; redacted evidence written under `.project-workflow/evidence/` |
| DeepSeek adapter focused tests | passed with synthetic HTTP transport; live synthetic calls are recorded below |

The full frontend audit still reports one high and one moderate advisory in
the development-only `vite -> postcss -> nanoid` chain. This does not enter the
nginx runtime image and is documented in [RELIABILITY.md](RELIABILITY.md).

## Compose and live evidence

The current Compose stack was rebuilt from the closure working tree with
`docker compose up --build --detach --wait`. Alembic, PostgreSQL, Redis, the
API, worker, cron, and frontend all started without deleting the PostgreSQL
volume.

The live health response reported both `database` and `redis` as `up` from
`http://127.0.0.1:8000/health` and through the frontend proxy at
`http://127.0.0.1:5173/api/health`. The API root returned its service envelope,
`GET /users/` returned the expected 401 authentication envelope, and the
frontend returned HTTP 200.

The long-running services now consistently use `restart: unless-stopped`.
Controlled Redis and nginx exits each incremented the container restart count,
returned to healthy/HTTP 200, and left the API reporting both dependencies up.
The one-shot migration container remains `restart: no` and exits successfully.

## Synthetic browser flow

Using a generated local-only password and synthetic records, Chromium verified:

1. Login and the real ticket list.
2. Ticket detail, Customer Info, Related Issues, and the attachment selector.
3. Uploading `browser-sample.txt` through a comment and downloading it again.
4. Starting AI analysis and observing the durable completed result.
5. Routing, My Settings, Users, and the 375px responsive ticket list.

The browser console reported no page errors. Screenshots are stored under
`docs/media/` and contain synthetic names/data only.

The current provider-selection QA also used synthetic local-only Admin and
Manager accounts. Admin saved the fake provider, ran its synthetic provider
test, and inspected the OpenRouter readiness/privacy state. Manager had no AI
settings navigation and received 403 responses for both settings read and
update attempts. At 375px wide, the settings page remained usable and
keyboard-focusable; the current screenshot is under the ignored
`.project-workflow/evidence/` directory.

## Scope notes and historical evidence

- The two legacy `UnsupportedButton` files and the tracked mockup sandbox live
  under the recoverable `docs/archive/` directory (not part of the release
  allowlist). The active frontend has no `UnsupportedButton` references and no
  mockup-sandbox source tree.
- GitHub Actions run `31474154749` passed all three jobs on commit `c6a8597`.
  The current pass verified the changed working tree locally and through the
  full-stack smoke; it does not claim that later commits have remote CI evidence.
- The deterministic fake analyzer is the verified local-demo provider. Real
  providers (OpenRouter, direct DeepSeek) have adapters and offline tests, but
  real-model output quality is **unverified** in v1: no authorized, budgeted
  evaluation was run and the automatic suite never calls a paid provider. Any
  historical live synthetic call is dated evidence, not a v1 quality claim.
- The database-backed AI settings surface is implemented for Admin and Super
  Admin. Provider/model provenance is snapshotted before enqueue and provider
  tests are audited without changing the active setting.
- Local attachment storage, unmanaged local secrets, and the absence of
  production metrics/traces are intentional v1 scope limits. They are not
  hidden production-readiness claims.
- A separate human learning quiz is outside this closure and is not part of the
  repository release gate.
