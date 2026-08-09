# AI-Oriented Customer Support Ticket System

Backend-first FastAPI project for a customer support platform in an AI/dev-tool domain.

**What this proves to employers / clients:** real backend engineering — users, JWT auth,
RBAC, ticket workflows, Redis, background jobs (RQ), routing, SLA, and tests — not only
prompt demos.

This repository is being built to practice production-shaped backend concepts with
FastAPI: authentication, role-based permissions, ticket workflows, comments,
database models, service-layer logic, Redis, background jobs, tests, and deployment
planning.

The project is intentionally backend-first. It is not a finished production UI/LLM
product yet. Core backend pieces are implemented and tested locally.

## Current Status

Implemented:

- FastAPI routers, service-layer business rules, Pydantic schemas, and SQLAlchemy
  persistence
- User registration, lookup, update, listing, soft deletion, password hashing,
  and explicit initial `SUPER_ADMIN` bootstrap
- JWT access tokens, refresh-session rotation, logout, and Bearer authentication
- Role-based authorization and agent role-transition safeguards
- Ticket CRUD, filtering, pagination, comments, assignment, claiming, and
  explicit start-work behavior
- Agent profiles with availability, capacity, and eligibility rules
- Deterministic least-loaded routing using workload, `last_assigned_at`, and
  user ID
- Atomic and idempotent automatic assignment with concurrency protection
- A dedicated RQ routing queue and periodic reconciliation of waiting tickets
- Priority-adjusted ticket-stage SLA deadlines, overdue filtering, and an
  idempotent periodic overdue scanner
- Redis login rate limiting and ticket-detail caching
- Per-user analysis-request rate limiting with atomic Redis counters
- Durable ticket summarization through API, SQL, Redis/RQ, worker, and
  SQL-backed read endpoints, with fake and OpenRouter analyzer modes
- Strict OpenRouter JSON-schema output, ZDR/data-collection routing controls,
  safe provider error categories, provenance, token accounting, and mocked HTTP
  tests
- Human/system audit actors and audit-event writes for important mutations
- A responsive Vite/React/TypeScript frontend using the real auth, ticket,
  routing-catalog, comment, history, workflow, and analysis APIs
- Automated tests for the main backend, cache, routing, reconciliation,
  start-work, concurrency, and SLA behavior
- Verified live development flows using FastAPI, Redis, RQ workers, SQL
  persistence, and RQ cron

In progress or not finished:

- Final portfolio documentation (architecture diagram, demo script) is not
  implemented

The detailed checked roadmap is in
[`notes/template.txt`](notes/template.txt).

## Project Idea

The app models a support system for an AI or developer-platform product.
Customers can create support tickets for issues such as login problems, billing
questions, API errors, model-output problems, or retrieval/RAG problems.

Support agents and admins can:

- view and filter tickets
- receive automatically routed tickets or claim/assign tickets manually
- control agent availability and routing capacity
- explicitly start work on an assigned ticket
- update status, priority, tags, and assignee fields
- add comments to the ticket conversation
- manage users according to role permissions

The routing policy uses managed departments and skills. A new ticket is
committed before an RQ routing job is enqueued. An eligible agent must have the
`AGENT` role, be active, available, below capacity, and belong to the ticket's
active department. More requested-skill matches rank first, but a
same-department agent with no matching skills remains a fallback. Existing
tie-breakers are workload, oldest assignment timestamp, then user ID. There is
no cross-department fallback.

## AI Assistance Scope

The first AI feature is intentionally narrow: summarize a frozen ticket and
bounded public-comment snapshot. Later versions may:

- classifying ticket priority
- suggesting reply drafts
- detecting similar or duplicate tickets

## Tech Stack

Current stack:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- PostgreSQL (Docker deployment) and SQLite (tests, quick local runs)
- Alembic schema migrations
- JWT access tokens
- Refresh-token sessions
- bcrypt password hashing
- Redis
- RQ background jobs
- OpenRouter Chat Completions through `httpx`
- Pytest
- React, TypeScript, Vite, and Vitest
- Docker and Docker Compose

## Backend Concepts Practiced

This project is designed to practice and explain:

- REST API design
- HTTP status codes
- database models and relationships
- authentication vs authorization
- password hashing
- JWT-based authentication
- refresh-token session rotation
- role-based access control
- service-layer architecture
- database CRUD operations
- soft deletion
- pagination, sorting, and filtering
- error handling
- testing backend behavior
- environment-based configuration
- cache TTL, invalidation, stale-data risk, and outage policy
- background queues, workers, retries, and reconciliation
- idempotency and concurrency-safe database updates
- application lifecycle and dependency health
- SLA deadline calculation

## API Overview

The current API is organized around these route groups:

### Users

- `POST /users/` - register a user
- `GET /users/` - list users with pagination and sorting
- `GET /users/{id}` - get one user
- `PATCH /users/{updated_user_id}` - update user fields
- `PATCH /users/{agent_id}/availability` - update an agent's own availability
- `PATCH /users/{agent_id}/agent-profile` - manager-level profile/capacity update
- `DELETE /users/{id}` - soft-delete one user
- `DELETE /users/` - admin-level bulk delete behavior

### Authentication

- `POST /auth/login` - login by nickname or email and receive tokens
- `POST /auth/refresh` - rotate a refresh token and receive a new token pair
- `POST /auth/logout` - revoke a refresh token

Protected routes use:

```text
Authorization: Bearer <access_token>
```

The authentication dependency decodes the JWT, loads the current user from the
database, and blocks deleted or banned users.

### Tickets

- `POST /tickets/` - create an unassigned customer ticket without internal
  routing metadata
- `GET /tickets/` - list tickets with pagination, sorting, and filters
- `GET /tickets/{id}` - get one ticket
- `PATCH /tickets/{ticket_id}` - update ticket workflow fields
- `DELETE /tickets/{id}` - soft-delete one ticket
- `DELETE /tickets/` - admin-level bulk delete behavior
- `POST /tickets/{ticket_id}/claim` - claim an unassigned ticket
- `POST /tickets/{ticket_id}/assign` - assign a ticket to an agent
- `POST /tickets/{ticket_id}/start-work` - move the assigned agent's ticket from
  `OPEN` to `IN_PROGRESS`
- `POST /tickets/{ticket_id}/analysis-results` - create or reuse a durable
  analysis request
- `GET /tickets/{ticket_id}/analysis-results` - read authorized analysis history
- `GET /analysis-results/{analysis_result_id}` - read one durable result

New customer tickets remain durable as `NEW`, unassigned, and without a
department until the support system or a Manager+ user classifies them.
Manager+ users can set `department_id` and optional `skill_ids` through the
ticket update endpoint. Saving valid routing metadata attempts to enqueue
automatic routing; periodic reconciliation can retry if Redis is unavailable.

### Routing Catalogs

- `GET /departments/` and `GET /skills/` - list active routing choices for
  authenticated users
- `POST /departments/` and `POST /skills/` - create catalog records as Manager+
- `PATCH /departments/{id}` and `PATCH /skills/{id}` - update catalog records
- `DELETE /departments/{id}` and `DELETE /skills/{id}` - archive records while
  preserving historical relationships
- `PATCH /users/{agent_id}/agent-profile` - configure the agent's department,
  skills, and capacity as Manager+

### Ticket Comments

- `GET /tickets/{ticket_id}/comments` - list comments for a ticket
- `POST /tickets/{ticket_id}/comments` - create a comment
- `GET /tickets/{ticket_id}/comments/{comment_id}` - get one comment
- `PATCH /tickets/{ticket_id}/comments/{comment_id}` - update a comment
- `DELETE /tickets/{ticket_id}/comments/{comment_id}` - soft-delete a comment

### Jobs

- `GET /jobs/{job_id}` - check the status of a background job
- `GET /jobs/` - admin-level job listing

There are two different job flows:

```text
Routing metadata update -> ticket_routing queue -> route_ticket() -> database assignment

Analysis request -> durable PENDING row -> ticket_jobs queue
    -> analyze_analysis_result(result_id)
    -> fake analyzer or OpenRouter
    -> durable COMPLETED/FAILED row
```

Automatic routing is implemented and database-owned: the queue delivers work,
but the database transaction decides whether assignment is still valid.

Analysis defaults to a deterministic fake summarizer. OpenRouter mode uses the
same provider-neutral interface and persists the requested provider, model,
prompt version, successful token counts, and validated summary. SQL—not the
expiring RQ job—is the permanent source of truth.

## Error Response Shape

Application, HTTP, and request-validation errors are returned in a shared
envelope:

```json
{
  "error": {
    "code": "ticket_not_found",
    "message": "Ticket not found"
  }
}
```

All routers, dependencies, and services raise shared domain exceptions, so
expected business failures always use this envelope with a stable `code`. The
`http_<status>` codes remain only as a fallback for raw `HTTPException`s raised
by the framework itself. `src/tests/test_error_contract.py` guards this
contract.

## Architecture and Data Flow

The synchronous request path is:

```text
HTTP request
    -> FastAPI router
    -> authentication dependency
    -> service-layer permissions and business rules
    -> SQLAlchemy database operation
    -> response schema
```

Automatic routing crosses a process boundary:

```text
Create and commit NEW ticket without internal routing metadata
    -> system classification or Manager+ triage sets department/skills
    -> enqueue stable routing job in Redis
    -> ticket_routing worker
    -> one database transaction:
         verify ticket is still routable
         select eligible least-loaded agent
         assign ticket and set OPEN
         update last_assigned_at and due_at
         write audit event
```

If enqueueing fails, the classified ticket is not deleted and its routing
metadata is not rolled back. RQ cron later finds bounded pages of
`NEW`/unassigned tickets that have a department and enqueues them again.
Unclassified tickets are deliberately excluded. Duplicate delivery is
expected, so database idempotency and transactional locking remain the final
correctness boundary.

Automatic routing and overdue detection use `SYSTEM` audit actors with no fake
human user ID. SLA deadlines combine the active status's base hours with the
priority multiplier: critical `0.25`, high `0.5`, normal `1.0`, and low `2.0`.
`GET /tickets?overdue=true` returns a bounded visible page and computes
`is_overdue` without writing. The periodic scanner is the separate write path
that records one overdue event per ticket.

Ticket details use Redis as a short-lived cache, while SQL remains the source of
truth. Reads fall back to SQL during cache failure, and successful mutations
invalidate the ticket key. Login rate limiting has a different policy: Redis
failure returns a service-unavailable error because the security check cannot be
enforced safely.

## Repository Structure

```text
main.py                 FastAPI app entrypoint
Dockerfile              Backend image (API, worker, cron share it)
compose.yaml            Full-stack Docker Compose definition
alembic/                Versioned PostgreSQL schema migrations
src/routers/            API route handlers
src/services/           Business logic and permission-aware workflows
src/db/                 SQLAlchemy engine, models, and database operations
src/models/             Pydantic request/response models
src/core/               Security, config, and logging helpers
src/constants/          Enums and shared constants
src/dependencies/       FastAPI dependencies
src/cache/              Redis/cache helper modules
src/analyzers/          Provider-neutral, fake, and OpenRouter analyzers
src/jobs/               RQ queue setup, job service logic, and worker tasks
src/exceptions/         Domain exception classes
src/tests/              Pytest test modules
site/                   Vite/React browser demo and frontend tests
keys/                   Local JWT key files
```

## Running with Docker

The whole stack — PostgreSQL, Redis, schema migrations, API, RQ worker, RQ
cron, and the frontend — starts with one command:

```bash
cp .env.example .env   # then set POSTGRES_PASSWORD and SUPERADMIN_* values
docker compose up --build
```

Startup order is enforced by health checks: Postgres and Redis must pass their
probes, the one-shot `migrate` service applies Alembic migrations, and only
then do the API, worker, and cron start. Create the initial superadmin once:

```bash
docker compose exec api python bootstrap_superadmin.py
```

Then open `http://localhost:5173` (frontend) or `http://localhost:8000/docs`
(API). Inside the compose network the services reach each other by name
(`db`, `redis`); only the API (8000) and frontend (5173) are published to the
host. Secrets stay out of images: `.env` is substituted at runtime and
`keys/` is mounted read-only.

Useful lifecycle commands:

```bash
docker compose ps                 # service status and health
docker compose logs -f worker     # follow one service's logs
docker compose down               # stop, keeping the Postgres volume
docker compose down -v            # full reset, deletes all data
```

## Running Locally (bare metal)

The bare-metal path keeps every process visible and is the better learning
setup. It needs five separate processes:

```text
Redis server
FastAPI API
RQ worker
RQ cron scheduler
Vite frontend
```

Create a `.env` file with local values. Do not commit real secrets:

```dotenv
DATABASE_URL=sqlite+pysqlite:///./tickets_system.db
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=keys/private.pem
JWT_PUBLIC_KEY_PATH=keys/public.pem
REFRESH_TOKEN_SECRET=replace-with-a-local-secret
ROUTING_RECONCILIATION_BATCH_SIZE=100
ROUTING_RECONCILIATION_INTERVAL_SECONDS=60
OVERDUE_SCAN_BATCH_SIZE=100
OVERDUE_SCAN_INTERVAL_SECONDS=60
ANALYZER_PROVIDER=fake
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_TIMEOUT_SECONDS=20
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

`ANALYZER_PROVIDER=fake` does not require an OpenRouter key. For a real
acceptance job, set `ANALYZER_PROVIDER=openrouter`, keep the key only in the
gitignored `.env` or process environment, and temporarily set
`OPENROUTER_MODEL=openai/gpt-oss-20b:free`. Every request requires parameter
support, denies provider data collection, and requires a Zero Data Retention
endpoint; do not relax those controls if the free model cannot be routed.

Manual acceptance status: **closed as an external blocker, accepted by
policy.** Checked 2026-07-23 and rechecked 2026-08-09 against OpenRouter's
public endpoint metadata (`/api/v1/models/openai/gpt-oss-20b/endpoints` and
`/api/v1/endpoints/zdr`): the zero-priced `openai/gpt-oss-20b:free` variant has
no ZDR-compliant endpoint — every ZDR-listed `gpt-oss-20b` endpoint is paid.
The project therefore accepts this gate as blocked rather than making a paid
request or weakening the privacy policy (`zdr=true`, `data_collection=deny`,
`require_parameters=true`). If a ZDR-compliant free endpoint appears later, the
runbook above (`ANALYZER_PROVIDER=openrouter`, one synthetic ticket, verify the
durable row) closes the gate in under an hour.

Start Redis and verify it responds:

```bash
redis-server
redis-cli ping
```

Start the API:

```bash
myvenv/bin/python -m uvicorn main:app --reload
```

Start one worker for both queues. Queue order gives routing jobs priority:

```bash
myvenv/bin/rq worker ticket_routing ticket_jobs \
  --url redis://localhost:6379/0
```

Start periodic waiting-ticket reconciliation:

```bash
myvenv/bin/rq cron src/jobs/cron.py \
  --url redis://localhost:6379/0
```

Start the browser application in another terminal:

```bash
cd site
npm install
cp .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend defaults to
`http://127.0.0.1:8000` for the API; change `VITE_API_BASE_URL` in
`site/.env` if needed. More frontend contract and verification details are in
[`site/README.md`](site/README.md).

Open the interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

By default, the application uses `tickets_system.db` in the repository root.
For an isolated smoke check, override it without editing source:

```bash
DATABASE_URL=sqlite+pysqlite:////tmp/tickets-smoke.db \
  myvenv/bin/python -m uvicorn main:app
```

Schema management is dialect-dependent: SQLite (tests, quick local runs) is
created/upgraded in the application lifespan, while PostgreSQL schemas are
owned by Alembic and applied explicitly with `alembic upgrade head` (the
compose `migrate` service runs it automatically).

### Initial superadmin

The bootstrap command refuses to run after the database already contains a
user. Provide the required `SUPERADMIN_*` environment values, then run:

```bash
myvenv/bin/python bootstrap_superadmin.py
```

### Tests

Run tests through the project virtual environment so imports and dependencies
match the application:

```bash
myvenv/bin/python -m pytest -q
```

Run the frontend tests and production build:

```bash
cd site
npm test
npm run build
```

For the automatic-routing slice:

```bash
myvenv/bin/python -m pytest -q \
  src/tests/test_agent_profiles.py \
  src/tests/test_ticket_routing.py \
  src/tests/test_routing_jobs.py \
  src/tests/test_routing_reconciliation.py \
  src/tests/test_start_work.py \
  src/tests/test_sla_deadlines.py
```

## Learning Notes

The main learning boundary in this project is:

```text
router -> dependency/auth -> service/business rules -> database operations
```

For background jobs, the learning boundary is:

```text
router -> jobs service -> RQ queue/Redis -> worker task
```

Automatic ticket routing uses its own `ticket_routing` queue. Routing is a
short, user-visible workflow and should not wait behind slower summarization
jobs on `ticket_jobs`. Start a routing worker with:

```bash
myvenv/bin/rq worker ticket_routing --url redis://localhost:6379/0
```

To let one local worker serve both queues while developing, list routing first
so it has priority:

```bash
myvenv/bin/rq worker ticket_routing ticket_jobs \
  --url redis://localhost:6379/0
```

Waiting-ticket reconciliation uses RQ's cron scheduler. Configure the bounded
page size and run interval in `.env` when the defaults are not suitable:

```text
ROUTING_RECONCILIATION_BATCH_SIZE=100
ROUTING_RECONCILIATION_INTERVAL_SECONDS=60
```

Start the scheduler in a separate process:

```bash
myvenv/bin/rq cron src/jobs/cron.py --url redis://localhost:6379/0
```

Each scheduled reconciliation reads at most one configured page of
`NEW`/unassigned tickets and enqueues independent jobs on `ticket_routing`, so a
routing worker must also be running. The same scheduler registers a bounded
overdue scan; repeated or concurrent scans preserve one audit event per ticket.

Routers receive HTTP requests and convert errors to HTTP responses.
Dependencies identify the current user.
Services decide whether an action is allowed and what business rule should run.
Database operations read and write SQLAlchemy models.

In larger production systems, the same separation is common, but the project
would usually add a real migration tool, structured observability, managed queue
infrastructure, stricter security controls, health/readiness endpoints, and
reproducible deployment configuration.

## Interview Summary

This project demonstrates a backend system with real application logic:
users, authentication, JWTs, refresh sessions, roles, database relationships,
ticket workflows, comments, service-layer authorization, Redis caching and rate
limiting, background jobs, automatic routing, reconciliation, concurrency
control, SLA deadlines, and a privacy-constrained asynchronous OpenRouter
summarization boundary.

It is useful for interview discussion because it shows both implemented backend
behavior and honest next steps toward a more production-like system: lifecycle
management, ticket-history APIs, durable analysis results, migrations,
real-provider acceptance, deployment, and observability.
