# AI-Oriented Customer Support Ticket System

Backend-first FastAPI project for a customer support platform: users, JWT
authentication, role-based permissions, ticket workflows, comments, automatic
agent routing, SLA deadlines, Redis caching/rate limiting, RQ background jobs,
and AI-assisted ticket summarization (fake analyzer or OpenRouter). A
Vite/React/TypeScript staff workspace in `site/` talks to the real API.

![ResolveAI staff ticket workspace showing SQL-backed tickets, customer info, and routing](docs/media/stage10-ticket-detail.png)

The screenshot uses synthetic local demo data. The complete safe recording
sequence is in [docs/DEMO.md](docs/DEMO.md).

## Tech Stack

- Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- PostgreSQL (Docker) / SQLite (tests, quick local runs)
- Redis, RQ (workers + cron scheduler)
- JWT (RS256) with refresh-token sessions, bcrypt password hashing
- OpenRouter Chat Completions via `httpx`
- Pytest; React, TypeScript, Vite, Vitest
- Docker and Docker Compose

## Quick Start (Docker)

The whole stack — PostgreSQL, Redis, migrations, API, worker, cron, and the
frontend — starts with one project command:

```bash
cp .env.example .env   # set POSTGRES_PASSWORD and SUPERADMIN_* values
./project.sh
```

Then open `http://localhost:5173` (frontend) or `http://localhost:8000/docs`
(API docs). The launcher builds the images, starts every service in the
background, waits for the stack to become healthy, and creates the configured
superadmin automatically when the database has no users. On later starts it
verifies the persisted administrator without overwriting it. It does not delete
or reset PostgreSQL data.

```bash
./project.sh status   # show every container and its health
./project.sh logs     # follow combined logs; Ctrl+C only stops viewing logs
./project.sh stop     # stop services and preserve the database volume
```

## Running Locally (bare metal)

Requires five processes: Redis, the API, an RQ worker, RQ cron, and Vite.

```bash
# .env: see .env.example; for local runs use SQLite + ANALYZER_PROVIDER=fake

redis-server                                            # 1
myvenv/bin/python -m uvicorn main:app --reload          # 2
myvenv/bin/rq worker ticket_routing ticket_jobs \
  --url redis://localhost:6379/0                        # 3 (routing first = priority)
myvenv/bin/rq cron src/jobs/cron.py \
  --url redis://localhost:6379/0                        # 4

cd site && npm install && cp .env.example .env && npm run dev   # 5
```

Open `http://127.0.0.1:5173`. Create the initial superadmin once with
`myvenv/bin/python bootstrap_superadmin.py` (requires `SUPERADMIN_*` env vars).

## Tests

```bash
myvenv/bin/python -m pytest -q      # backend
cd site && npm test && npm run build  # frontend
```

## API Overview

- **Users** — register, list, get, update, agent availability/profile, soft delete
- **Auth** — `POST /auth/login`, `/auth/refresh`, `/auth/logout`; Bearer JWT
- **Tickets** — SQL-backed search/filter/pagination, My Queue, claim/assign/
  start-work, comments, ticket-scoped customer info, related issues, and
  durable AI analysis results
- **Staff workspace** — role-aware Users, Routing catalogs, My Settings, agent
  availability, secure comment attachments, and recipient-only notifications
- **Jobs** — background job status and listing

Errors use a shared envelope: `{ "error": { "code", "message" } }`.

## Detailed documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Permissions](docs/PERMISSIONS.md)
- [Ticket workflow](docs/TICKET_WORKFLOW.md)
- [API examples](docs/API_EXAMPLES.md)
- [Reliability and security](docs/RELIABILITY.md)
- [Attachment contract](docs/ATTACHMENTS.md)
- [Five-minute demo script](docs/DEMO.md)
- [Stage 10 acceptance evidence](docs/ACCEPTANCE.md)

## Repository Structure

```text
main.py                 FastAPI app entrypoint
Dockerfile / compose.yaml   Full-stack deployment
alembic/                PostgreSQL schema migrations
src/routers/            API route handlers
src/services/           Business logic and permissions
src/db/                 SQLAlchemy engine, models, operations
src/models/             Pydantic request/response models
src/core/               Security, config, logging
src/jobs/               RQ queues, worker tasks, cron
src/analyzers/          Fake and OpenRouter analyzers
src/cache/              Redis helpers
src/tests/              Pytest suite
site/                   Vite/React frontend (see site/README.md)
```

## How It Works

Synchronous requests follow `router -> auth dependency -> service -> database`.
Two flows cross a process boundary through Redis/RQ:

- **Routing**: a classified ticket (`department_id` set) is enqueued on
  `ticket_routing`; a worker assigns it to the eligible least-loaded agent in
  one idempotent database transaction. RQ cron re-enqueues tickets whose
  enqueue failed earlier.
- **Analysis**: a durable PENDING row is created, processed on `ticket_jobs`
  by the fake analyzer or OpenRouter, and stored as COMPLETED/FAILED — SQL is
  the source of truth, not the RQ job.

Redis also provides ticket-detail caching (SQL fallback on failure) and login
rate limiting (fails closed). SLA deadlines combine status base hours with a
priority multiplier; a periodic scanner records one overdue event per ticket.
