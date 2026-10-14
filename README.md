# ResolveAI — AI-Oriented Customer Support Ticket System

Backend-first FastAPI project for a customer support platform: users, JWT
authentication, role-based permissions, ticket workflows, comments, automatic
agent routing, SLA deadlines, Redis caching/rate limiting, RQ background jobs,
and AI-assisted ticket summarization. A Vite/React/TypeScript staff workspace in
`site/` talks to the real API.

A staff workspace screenshot (kept under the local `docs/media/` directory that
is intentionally **not** part of the release allowlist) uses synthetic local
demo data. Acceptance evidence is in [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

## Tech stack

- Python 3.13, FastAPI, Pydantic, SQLAlchemy, Alembic
- PostgreSQL 16 (Docker) / SQLite (tests, quick local runs)
- Redis, RQ (worker + retry scheduler + `rq cron`)
- JWT (RS256) with refresh-token sessions; Argon2 password hashing (legacy bcrypt verification)
- OpenRouter and direct DeepSeek adapters via `httpx` (fake analyzer is the verified default)
- Pytest; React, TypeScript, Vite, Vitest
- Docker and Docker Compose

---

## Run it right now (Docker)

Full step-by-step from a fresh checkout.

### 1. Create local configuration

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- `POSTGRES_PASSWORD` — any local password
- `REFRESH_TOKEN_SECRET` — `openssl rand -hex 32`
- `SUPERADMIN_PASSWORD` — a local password (≥ 15 chars), and the other `SUPERADMIN_*` values

Leave `DEEPSEEK_API_KEY` / `OPENROUTER_API_KEY` empty. The active provider is
seeded to the local **fake** analyzer, so no paid call is needed to run or demo.

### 2. Generate the JWT signing key pair

```bash
mkdir -p keys
umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/private.pem
openssl pkey -in keys/private.pem -pubout -out keys/public.pem
```

Keep `.env` and `keys/private.pem` out of Git and screenshots. New keys
invalidate existing access tokens; if this installation already used a pair,
restore the original instead of regenerating.

### 3. Start the whole stack

```bash
./project.sh
```

This builds images and starts PostgreSQL, Redis, migrations, the API, an RQ
worker, `rq cron`, and the frontend; waits for health; and creates the configured
superadmin when the database has no users. It does not reset PostgreSQL data.

```bash
./project.sh status      # every container and its health
./project.sh logs        # follow combined logs (Ctrl+C only stops viewing)
./project.sh demo-data   # seed synthetic demo data
./project.sh stop        # stop services, keep the database volume
```

### 4. Open it

- Frontend (staff workspace): <http://localhost:5173>
- API docs (Swagger): <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Background readiness: <http://localhost:8000/health/ready>

Sign in with the `SUPERADMIN_NICKNAME` / `SUPERADMIN_PASSWORD` you set. Both
published ports bind to **loopback only** by default; see
[docs/OPERATIONS.md](docs/OPERATIONS.md) before exposing the stack.

---

## Run it locally (bare metal)

Requires five processes: Redis, the API, an RQ worker, `rq cron`, and Vite.

```bash
python3 -m venv myvenv && myvenv/bin/pip install -r requirements-dev.txt
cp .env.example .env      # set values as above; keys/ generated as above

redis-server                                                        # 1
myvenv/bin/alembic upgrade head                                     # schema
myvenv/bin/python -m uvicorn main:app --reload                      # 2
myvenv/bin/rq worker ticket_jobs ticket_routing \
  --with-scheduler --url redis://localhost:6379/0                   # 3
myvenv/bin/rq cron src/jobs/cron.py --url redis://localhost:6379/0  # 4

cd site && npm install && cp .env.example .env && npm run dev       # 5
```

Create the initial superadmin once with
`myvenv/bin/python bootstrap_superadmin.py` (requires the `SUPERADMIN_*` vars).

---

## Test and verify

```bash
# Backend (isolated: no dotenv, Redis off, fake provider)
REDIS_ENABLED=false myvenv/bin/python -m pytest -q

# Same suite with the PostgreSQL 16 concurrency cases enabled
TEST_POSTGRES_URL=postgresql+psycopg://user:pw@127.0.0.1:5432/postgres \
TEST_POSTGRES_ALLOW_DESTRUCTIVE=1 \
  myvenv/bin/python -m pytest -q

# Frontend
cd site && npm test -- --run && npm run build

# Lint / compile / whitespace
myvenv/bin/ruff check main.py src scripts bootstrap_superadmin.py
myvenv/bin/python -m compileall -q main.py src scripts bootstrap_superadmin.py
git diff --check
```

Integration and release gates (opt-in, disposable targets only):

```bash
# All safe checks at once, with redacted evidence under .project-workflow/evidence/
myvenv/bin/python scripts/verify_release.py

# Real Redis + RQ + fake provider lifecycle (needs a loopback Redis)
SMOKE_REDIS_URL=redis://127.0.0.1:6379/0 myvenv/bin/python scripts/smoke_redis_rq.py

# Full nginx -> API -> PostgreSQL/Redis stack: readiness green/red/green,
# uploads, token refresh, and upstream rediscovery. Needs Docker.
myvenv/bin/python scripts/smoke_http_stack.py

# Migrations on an empty and a populated PostgreSQL database
TEST_POSTGRES_URL=postgresql+psycopg://user:pw@host:5432/postgres \
TEST_POSTGRES_ALLOW_DESTRUCTIVE=1 \
  myvenv/bin/python scripts/verify_migrations.py

# Build the reviewed v1 source snapshot with a manifest and checksum
myvenv/bin/python scripts/build_release.py
```

The PostgreSQL integration fixture and the migration/smoke scripts refuse to
run against a target they cannot prove is disposable: they create and drop their
own database (or require an explicit opt-in), never touch a shared database, and
never read a developer's private `.env`.

---

## How it works

Synchronous requests follow `router -> auth dependency -> service -> database`.
Two flows cross a process boundary through Redis/RQ, and SQL is the source of
truth when a worker is delayed or restarted.

- **Synchronous** — e.g. `GET /tickets/{id}`: the auth dependency verifies the
  Bearer JWT and loads the caller; the service checks the caller's read access;
  `src/db/operations` reads the ticket (Redis cache when available, SQL
  fallback); the router returns the Pydantic response. No background process is
  involved, so a Redis outage degrades this to a slower SQL read.
- **Background (analysis)** — the API first writes a durable `PENDING`
  `AnalysisResult` row that snapshots the ticket input and the
  provider/model/prompt provenance, then enqueues the stable RQ job
  `analyze-result-<id>`. A worker claims it under a lease, runs the snapshot's
  adapter (fake by default), and stores `COMPLETED`/`FAILED` back on the row.
  The browser polls the row, not the RQ job. A bounded reconciler re-dispatches
  clearly-unstarted work and moves an interrupted provider call to the safe
  terminal `provider_result_unknown` state for a human retry.
- **Background (routing)** — a classified ticket is enqueued on
  `ticket_routing`; a worker assigns it to the eligible least-loaded agent in
  one idempotent transaction. Routing and analysis reconciliation scans are
  fair (least-recently-attempted first), so no blocked page starves later work.

Redis also provides ticket-detail caching (SQL fallback) and login rate limiting
(fails closed). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full
boundaries.

### Health vs readiness

- `GET /health` — API liveness: the process answered and PostgreSQL (and Redis
  when enabled) are reachable.
- `GET /health/ready` — additionally requires a fresh worker heartbeat, worker
  subscriptions to every expected queue, and fresh scheduler/cron activity. A
  stuck worker is therefore visible even while read-only API traffic stays up.

---

## API overview

- **Users** — register, list, get, update, agent availability/profile, soft delete
- **Auth** — `POST /auth/login`, `/auth/refresh`, `/auth/logout`; Bearer JWT
- **Tickets** — search/filter/pagination, My Queue, claim/assign/start-work,
  comments, ticket-scoped customer info, related issues, durable AI analysis
- **AI settings** — Admin/Super Admin-only global provider/model selection
  (fake, OpenRouter, direct DeepSeek); provider keys never cross the API
- **Staff workspace** — role-aware Users, Routing catalogs, My Settings, agent
  availability, secure comment attachments, recipient-only notifications
- **Jobs** — background job status and listing
- **Health** — `/health` (liveness) and `/health/ready` (background readiness)

Errors use a shared envelope: `{ "error": { "code", "message" } }`.

---

## Scope and limitations (v1)

This is a **local** interview project. Explicit limits, not hidden claims:

- The deterministic **fake** analyzer is the verified demo provider.
  Real-provider (OpenRouter/DeepSeek) output quality is **unverified**: no
  authorized, budgeted real-model evaluation is included, and the automatic
  suite never calls a paid provider.
- Ports bind to loopback. Public hosting (TLS, trusted proxies, abuse/rate
  limits, backup/restore, monitoring) is out of scope and would be required
  before real users; see the hosting gates in [docs/OPERATIONS.md](docs/OPERATIONS.md).
- Attachments use local filesystem storage (a Compose volume), not object
  storage.
- No production metrics/traces; readiness is the operational signal provided.
- No test suite proves the absence of every possible bug.

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Permissions](docs/PERMISSIONS.md)
- [Ticket workflow](docs/TICKET_WORKFLOW.md)
- [API examples](docs/API_EXAMPLES.md)
- [Reliability and security](docs/RELIABILITY.md)
- [Operations, readiness, and hosting gates](docs/OPERATIONS.md)
- [AI analysis evaluation](docs/AI_EVALUATION.md)
- [Attachment contract](docs/ATTACHMENTS.md)
- [Interview checks and remaining risks](docs/INTERVIEW_CHECK.md)
- [Interview demo and operator handoff](docs/INTERVIEW_DEMO.md)
- [Final v1 acceptance evidence](docs/ACCEPTANCE.md)

## Repository structure

```text
main.py                     FastAPI app entrypoint
Dockerfile / compose.yaml   Full-stack deployment
compose.smoke.yaml          Task-owned disposable stack for the nginx smoke
alembic/                    PostgreSQL schema migrations
src/routers/                API route handlers
src/services/               Business logic and permissions
src/db/                     SQLAlchemy engine, models, operations
src/models/                 Pydantic request/response models
src/core/                   Security, config, logging
src/jobs/                   RQ queues, worker tasks, cron, readiness
src/analyzers/              Fake, OpenRouter, and DeepSeek analyzers
src/cache/                  Redis helpers
src/storage/                Local attachment storage
src/tests/                  Pytest suite
scripts/                    Verification, smoke, migration, and packaging tools
site/                       Vite/React frontend (see site/README.md)
```
