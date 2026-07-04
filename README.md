# AI Customer Support Ticket System

Demo backend project for an AI-assisted customer support platform.

The project is being built as a learning and interview-preparation project. The goal is to show how a real backend system can handle users, authentication, roles, support tickets, ticket workflow, and later AI-assisted ticket analysis.

## Current Status

This is a work-in-progress demo version.

Implemented or started:

- FastAPI application structure
- SQLAlchemy database models
- User and ticket CRUD logic
- Service layer and database operation layer
- Role-based permission checks
- Password hashing on user creation and password updates
- First registered user bootstrap as `SUPER_ADMIN`
- JWT access-token login and Bearer-token authentication dependency
- Refresh session model and refresh-token rotation flow
- Soft delete behavior for users and tickets
- User update rules for protected fields such as role, status, and password
- Basic tests for users, tickets, and auth

Planned next:

- Complete auth flow: logout and current-user endpoint
- Ticket comments
- Ticket history/events
- Stronger workflow validation
- Redis caching and rate limiting
- Background worker for AI jobs
- LLM-assisted ticket summary, priority classification, and reply suggestion
- Docker Compose setup
- Small React + JavaScript frontend demo

## Project Idea

Users can create support tickets for problems such as login issues, billing problems, API errors, or model-output problems. Support agents can view, assign, update, and resolve tickets. Admin users can manage users and oversee the whole system.

The AI part will help support agents by:

- summarizing long tickets
- classifying ticket priority
- suggesting reply drafts
- detecting similar or duplicate tickets

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite for the current local demo
- Pydantic
- bcrypt password hashing
- JWT
- Pytest

Planned:

- Redis
- Background worker
- Docker / Docker Compose
- React + JavaScript frontend
- LLM API integration

## Backend Concepts Practiced

This project is designed to demonstrate:

- REST API design
- HTTP status codes
- database models and relationships
- authentication vs authorization
- password hashing
- JWT-based auth
- role-based access control
- service-layer architecture
- database CRUD operations
- error handling
- testing
- environment-based configuration

## Planned Frontend

The frontend will be a small React + JavaScript client, not a large production UI.

Its purpose is to show how the frontend and backend connect:

- register and login forms
- storing and sending access tokens
- ticket list page
- ticket detail page
- create-ticket form
- role-based actions for agents/admins
- later: an AI analysis panel for summaries and reply suggestions

## Running Locally

Create and activate a virtual environment, then install the project dependencies used by the local environment.

Start the API:

```bash
myvenv/bin/python -m uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

The interactive docs can be used to test the API endpoints.

## API Progress

Current backend endpoints are organized around:

- `/users` for registration, user lookup, user updates, soft deletion, and admin-level user listing/deletion
- `/tickets` for ticket creation, lookup, updates, assignment-related fields, workflow state, and soft deletion
- `/auth/login` for password login with nickname or email
- `/auth/refresh` for rotating a refresh token and returning a new access token pair

Protected routes use the standard `Authorization: Bearer <access_token>` header. The auth dependency decodes the JWT, loads the current user from the database, and blocks deleted or banned users.

User-management behavior currently includes:

- new users get hashed passwords before they are stored
- the first registered user becomes `SUPER_ADMIN`
- normal profile fields can be updated through the user update service
- password updates are re-hashed before saving
- role, status, and deletion-related updates are treated as protected admin-level changes
- `created_at` and `updated_at` are system-managed fields, not client-managed fields

## Repository Structure

```text
main.py                 FastAPI app entrypoint
src/routers/            API route handlers
src/services/           Business logic
src/db/                 SQLAlchemy engine, models, and operations
src/models/             Pydantic request/response models
src/core/               Security, config, logging helpers
src/constants/          Enums and shared helpers
src/dependencies/       FastAPI dependencies
src/tests/              Tests
```

## Interview Summary

This project shows how I am building a backend system with real application logic: users, authentication, roles, database relationships, ticket workflows, and AI-assisted support features. It is intentionally backend-first, with a small frontend planned to demonstrate full request/response flow between a web client and the API.
