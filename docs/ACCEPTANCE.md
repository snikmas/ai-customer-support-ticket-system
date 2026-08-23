# Final v1 acceptance evidence

Recorded locally on 2026-08-24 during the ResolveAI provider-selection closure.
The existing closure changes remain in the working tree and are listed in the
root `TODO.md`; this document distinguishes current checks from historical
Compose/browser evidence.

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

- The two legacy `UnsupportedButton` files and the tracked mockup sandbox were
  moved into the recoverable [archive](archive/README.md). The active frontend
  has no `UnsupportedButton` references and no mockup-sandbox source tree.
  Physical deletion was refused by the repository safety hook, so the exact
  source remains recoverable in `docs/archive/`.
- GitHub Actions run `31474154749` passed all three jobs on commit `c6a8597`.
  The current closure pass additionally verified the changed working tree
  locally; it does not claim that the later commits have remote CI evidence.
- The deterministic fake analyzer remains the verified local-demo provider.
  Direct DeepSeek was also exercised with synthetic live requests during this
  closure pass: the provider test and two queued analyses completed, including
  a provenance check where a pending DeepSeek job completed after the global
  setting was changed back to fake. OpenRouter has adapters and automated tests,
  but its live test and queued analysis remain pending until its key is
  configured. The recorded DeepSeek calls stayed below the approved US$0.10
  aggregate spend limit.
- The database-backed AI settings surface is implemented for Admin and Super
  Admin. Provider/model provenance is snapshotted before enqueue and provider
  tests are audited without changing the active setting.
- Local attachment storage, unmanaged local secrets, and the absence of
  production metrics/traces are intentional v1 scope limits. They are not
  hidden production-readiness claims.
- The final “Mary can explain” item is a human learning proof, not something
  the repository can honestly self-certify.
