# Customer Support Ticket System

Learning backend project for a customer support ticket system.

This repository is being built to practice real backend engineering concepts with
FastAPI: users, authentication, role-based permissions, ticket workflows,
comments, database models, service-layer logic, Redis, background jobs, tests,
and deployment.

The project is intentionally backend-first. It is not a finished production
system yet.

## Current Status

Implemented or started:

- FastAPI application with router-based structure
- SQLAlchemy models and local SQLite database setup
- User registration, lookup, update, listing, and soft deletion
- Explicit environment-driven command for initial `SUPER_ADMIN` bootstrap
- Password hashing for user creation and password updates
- JWT access-token login with `Authorization: Bearer <access_token>`
- Refresh-token session model and token rotation flow
- Logout endpoint that revokes a refresh token
- Role-based permission checks in the service layer
- Ticket creation, lookup, update, assignment, claiming, listing, and soft deletion
- Ticket comments with create, read, update, delete, visibility, source, and soft-delete fields
- Pagination and sorting support on user, ticket, and comment listing routes
- Basic custom domain exception handling for some comment flows
- Redis helper modules started for future caching/rate-limiting work
- RQ background-job structure started with a temporary ticket-analysis job name
- Job API endpoints started for creating an analysis job and checking job status
- Pytest test modules for users, auth, tickets, and comments

Not finished yet:

- Consistent error response shape across all routers
- Complete ticket history/event log
- Stronger ticket workflow validation
- Full Redis integration for caching and rate limiting
- Running and verifying an RQ worker process end-to-end
- A complete, non-AI background-job workflow
- Docker / Docker Compose setup
- Small frontend demo

## Project Idea

The app models a support system for an AI or developer-platform product.
Customers can create support tickets for issues such as login problems, billing
questions, API errors, model-output problems, or retrieval/RAG problems.

Support agents and admins can:

- view and filter tickets
- claim or assign tickets
- update status, priority, tags, and assignee fields
- add comments to the ticket conversation
- manage users according to role permissions

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

## API Overview

The current API is organized around these route groups:

### Users

- `POST /users/` - register a user
- `GET /users/` - list users with pagination and sorting
- `GET /users/{id}` - get one user
- `PATCH /users/{updated_user_id}` - update user fields
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

- `POST /tickets/` - create a ticket
- `GET /tickets/` - list tickets with pagination, sorting, and filters
- `GET /tickets/{id}` - get one ticket
- `PATCH /tickets/{ticket_id}` - update ticket workflow fields
- `DELETE /tickets/{id}` - soft-delete one ticket
- `DELETE /tickets/` - admin-level bulk delete behavior
- `POST /tickets/{ticket_id}/claim` - claim an unassigned ticket
- `POST /tickets/{ticket_id}/assign` - assign a ticket to an agent
- `POST /tickets/{ticket_id}/analysis-jobs` - enqueue a background analysis job

### Ticket Comments

- `GET /tickets/{ticket_id}/comments` - list comments for a ticket
- `POST /tickets/{ticket_id}/comments` - create a comment
- `GET /tickets/{ticket_id}/comments/{comment_id}` - get one comment
- `PATCH /tickets/{ticket_id}/comments/{comment_id}` - update a comment
- `DELETE /tickets/{ticket_id}/comments/{comment_id}` - soft-delete a comment

### Jobs

- `GET /jobs/{job_id}` - check the status of a background job

The current job flow is intentionally minimal:

```text
API request -> RQ queue in Redis -> worker task -> temporary job status
```

The current job uses placeholder output to verify RQ mechanics. It is not AI
assistance. Any future AI result should be stored in the database, not only in
Redis.

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

Use the existing local virtual environment:

```bash
myvenv/bin/python -m uvicorn main:app --reload
```

Open the interactive API docs:

```text
http://127.0.0.1:8000/docs
```

The app loads environment configuration from `.env`. The local database file is
created automatically by the current startup code.

## Learning Notes

The main learning boundary in this project is:

```text
router -> dependency/auth -> service/business rules -> database operations
```

For background jobs, the learning boundary is:

```text
router -> jobs service -> RQ queue/Redis -> worker task
```

Routers receive HTTP requests and convert errors to HTTP responses.
Dependencies identify the current user.
Services decide whether an action is allowed and what business rule should run.
Database operations read and write SQLAlchemy models.

In larger production systems, the same separation is common, but the project
would usually add migrations, stronger observability, background queues,
centralized error responses, stricter security controls, and deployment
configuration.

## Interview Summary

This project demonstrates a backend system with real application logic:
users, authentication, JWTs, refresh sessions, roles, database relationships,
ticket workflows, comments, service-layer authorization, Redis, and background
job processing. AI assistance is a future extension after this core project is
complete.

It is useful for interview discussion because it shows both implemented backend
behavior and clear next steps toward a more production-like system.
