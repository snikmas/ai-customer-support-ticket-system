# Stage 10 acceptance evidence

Recorded locally on 2026-08-11 after the Stage 10 implementation pass.

## Automated checks

| Check | Result |
| --- | --- |
| `myvenv/bin/python -m pytest -q` | 313 passed |
| `cd site && npm test -- --run` | 4 files, 12 tests passed |
| `cd site && npm run build` | passed |
| `cd site && npm audit --omit=dev` | 0 vulnerabilities |
| `docker compose config --quiet` | passed |
| `python -m compileall ...`, `bash -n project.sh`, `git diff --check` | passed |

The full frontend audit still reports one high and one moderate advisory in
the development-only `vite -> postcss -> nanoid` chain. This does not enter the
nginx runtime image and is documented in [RELIABILITY.md](RELIABILITY.md).

## Compose and live evidence

`./project.sh start` rebuilt the images, ran Alembic, waited for health checks,
and verified the existing configured Super Admin. `./project.sh stop` then
`./project.sh start` stopped and restored the stack without deleting the
PostgreSQL volume.

The live health response reported both `database` and `redis` as `up` when
queried with `curl --noproxy '*' http://127.0.0.1:8000/health`. The Compose
services `api`, `db`, `redis`, `worker`, `cron`, and `frontend` were healthy or
running. A plain host `curl` was routed through the configured proxy and
returned 502 before reaching Uvicorn; Docker's in-container health probe and
the proxy-bypassed request both returned 200. Worker evidence included a
completed AI analysis request and routing/overdue scanner log entries.

## Synthetic browser flow

Using a generated local-only password and synthetic records, Chromium verified:

1. Login and the real ticket list.
2. Ticket detail, Customer Info, Related Issues, and the attachment selector.
3. Uploading `browser-sample.txt` through a comment and downloading it again.
4. Starting AI analysis and observing the durable completed result.
5. Routing, My Settings, Users, and the 375px responsive ticket list.

The browser console reported no page errors. Screenshots are stored under
`docs/media/` and contain synthetic names/data only.

## Remaining gates

- The two legacy `UnsupportedButton` files and the tracked mockup sandbox were
  moved into the recoverable [archive](archive/README.md). The active frontend
  has no `UnsupportedButton` references and no mockup-sandbox source tree.
  Physical deletion was refused by the repository safety hook, so the exact
  source remains recoverable in `docs/archive/`.
- GitHub Actions has been added but has not run remotely because this pass did
  not push or open a PR.
- The final “Mary can explain” item is a human learning proof, not something
  the repository can honestly self-certify.
