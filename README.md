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
- Human/system audit actors and audit-event writes for important mutations
- Automated tests for the main backend, cache, routing, reconciliation,
  start-work, concurrency, and SLA behavior
- A verified live development flow using FastAPI, Redis, an RQ worker, and RQ
  cron for automatic routing

In progress or not finished:

- Some routers still translate raw `PermissionError` and `ValueError` instead of
  using the shared domain exceptions
- The application still initializes the database at import time and does not
  have meaningful health endpoints
- Ticket history is recorded internally, but a complete permission-aware
  history API is not implemented
- The placeholder ticket-inspection job has incomplete persistent-result logic
- LLM ticket summarization is not implemented
- Docker / Docker Compose, a frontend demo, and final portfolio documentation
  are not implemented

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

## Future Extension: AI Assistance

AI assistance is deliberately out of scope until the core support system is
finished. A later version may help support agents by:

- summarizing long ticket conversations
- classifying ticket priority
- suggesting reply drafts
- detecting similar or duplicate tickets

## Tech Stack

Current stack:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite for local development
- JWT access tokens
- Refresh-token sessions
- bcrypt password hashing
- Redis
- RQ background jobs
- Pytest

Planned after the core project:

- Docker / Docker Compose
- LLM API integration and AI-assisted ticket analysis
- Small web frontend

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

- `POST /tickets/` - create a ticket with an active `department_id` and optional
  `skill_ids`
- `GET /tickets/` - list tickets with pagination, sorting, and filters
- `GET /tickets/{id}` - get one ticket
- `PATCH /tickets/{ticket_id}` - update ticket workflow fields
- `DELETE /tickets/{id}` - soft-delete one ticket
- `DELETE /tickets/` - admin-level bulk delete behavior
- `POST /tickets/{ticket_id}/claim` - claim an unassigned ticket
- `POST /tickets/{ticket_id}/assign` - assign a ticket to an agent
- `POST /tickets/{ticket_id}/start-work` - move the assigned agent's ticket from
  `OPEN` to `IN_PROGRESS`
- `POST /tickets/{ticket_id}/analysis-jobs` - enqueue a background analysis job

Creating a ticket also attempts to enqueue automatic routing after the database
commit. If Redis or enqueueing fails, the ticket remains durable as
`NEW`/unassigned and periodic reconciliation can retry it later.

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
Ticket creation -> ticket_routing queue -> route_ticket() -> database assignment

Analysis request -> ticket_jobs queue -> inspect_ticket() -> temporary RQ result
```

Automatic routing is implemented and database-owned: the queue delivers work,
but the database transaction decides whether assignment is still valid.

The analysis job is still a placeholder, not AI assistance. Its persistent
`AnalysisResult` path and read endpoint are incomplete and should not yet be
treated as a finished feature.

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

Some older ticket and job routes still need to migrate from broad built-in
exceptions to precise domain exceptions, so not every error code is final.

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
Create and commit NEW ticket
    -> enqueue stable routing job in Redis
    -> ticket_routing worker
    -> one database transaction:
         verify ticket is still routable
         select eligible least-loaded agent
         assign ticket and set OPEN
         update last_assigned_at and due_at
         write audit event
```

If enqueueing fails, the committed ticket is not deleted or rolled back.
RQ cron later finds bounded pages of waiting `NEW`/unassigned tickets and
enqueues them again. Duplicate delivery is expected, so database idempotency and
transactional locking remain the final correctness boundary.

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
src/routers/            API route handlers
src/services/           Business logic and permission-aware workflows
src/db/                 SQLAlchemy engine, models, and database operations
src/models/             Pydantic request/response models
src/core/               Security, config, and logging helpers
src/constants/          Enums and shared constants
src/dependencies/       FastAPI dependencies
src/cache/              Redis/cache helper modules
src/jobs/               RQ queue setup, job service logic, and worker tasks
src/exceptions/         Domain exception classes
src/tests/              Pytest test modules
keys/                   Local JWT key files
```

## Running Locally

The current development stack needs four separate processes:

```text
Redis server
FastAPI API
RQ worker
RQ cron scheduler
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
```

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

The current application creates or upgrades its local schema while `main.py` is
imported. Moving this work to an explicit migration/startup boundary is still a
roadmap item.

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
short, user-visible workflow and should not wait behind slower ticket inspection
or future LLM jobs on `ticket_jobs`. Start a routing worker with:

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
control, and SLA deadlines. AI assistance remains a future extension after the
core project is stable.

It is useful for interview discussion because it shows both implemented backend
behavior and honest next steps toward a more production-like system: lifecycle
management, ticket-history APIs, durable analysis results, migrations,
deployment, and observability.
