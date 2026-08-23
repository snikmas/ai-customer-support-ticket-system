---
name: verify-resolveai
description: Verify the ResolveAI FastAPI and React staff workspace through its real local checks and user-facing runtime paths.
---

# Verify ResolveAI

Use this skill for release checks or when a change needs evidence from the
running ResolveAI application. The primary surface is the browser staff
workspace; the FastAPI API and RQ worker are supporting runtime surfaces.

## Launch

For a full local stack, use the repository launcher:

    ./project.sh

It starts PostgreSQL, Redis, migrations, API, worker, cron, and the frontend.
Readiness is the launcher health output plus curl -fsS
http://127.0.0.1:8000/health. The frontend is at http://127.0.0.1:5173.
Do not reset volumes or recreate the user's .env.

For code-only checks, no server is required:

    myvenv/bin/python scripts/verify_release.py

## Doctor

Run this before driving a stack that appears unhealthy:

    ./project.sh status
    curl -fsS http://127.0.0.1:8000/health
    docker compose ps

Confirm that the reported containers belong to this checkout before using
runtime commands. Never kill a process by name.

## Drive

Drive the browser through stable routes and accessible names. Existing
features include login, ticket list/detail, users, routing, and personal
settings. The ResolveAI closure adds /ai-settings for Admin and Super Admin.

For the provider slice, use synthetic ticket content only:

1. Log in as a synthetic Admin or Super Admin.
2. Open AI settings and record the visible provider/model and readiness state.
3. Change provider/model, save, and confirm the success state after refresh.
4. Run the provider test and confirm its result does not change the active
   selection.
5. Create an analysis, record the visible result, and inspect durable
   provider/model provenance through the authenticated API.
6. Repeat authorization as Manager and Agent; both must receive a forbidden
   state and no settings data.

## Evidence

Canonical code-check evidence is written under
.project-workflow/evidence/ by scripts/verify_release.py; that directory is
ignored and must not contain credentials. Browser evidence must capture the
action and resulting state, not only the final screen. Pair UI evidence with
API/SQL evidence for setting version, audit event, and analysis provenance.
For provider tests, retain only safe status/model/token metadata and synthetic
input identifiers; never save prompts, outputs, keys, or raw upstream bodies.

## Cleanup

If this run started the stack, stop only the services started by this checkout:

    ./project.sh stop

This preserves the database volume. Do not remove volumes as part of ordinary
verification. Evidence under .project-workflow/evidence/ survives cleanup.

## Helpers

The repeatable helper is:

    myvenv/bin/python scripts/verify_release.py [--compose]

The default command never makes provider calls. Live provider verification is
an explicit later QA action with synthetic data and the approved aggregate
spending limit.
