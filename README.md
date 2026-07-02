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
- Password hashing
- JWT access token helpers
- Refresh session model and refresh-token flow
- Basic tests for users, tickets, and auth

Planned next:

- Complete auth flow: login, refresh, logout, current-user endpoint
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
