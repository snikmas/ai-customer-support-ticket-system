# ResolveAI frontend

This directory contains the staff-workspace browser application for the real FastAPI backend.
It is a Vite, React, and TypeScript application; it does not use mock ticket
data.

## Run locally

Start FastAPI, Redis, and an RQ worker as described in the repository README.
The default browser/API pair is:

```text
frontend  http://127.0.0.1:5173
API       http://127.0.0.1:8000
```

Then start the frontend:

```bash
cd site
npm install
cp .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` in `site/.env` when FastAPI uses another address. The
backend's `FRONTEND_ORIGINS` setting must contain the exact frontend origins;
the local defaults allow `localhost:5173` and `127.0.0.1:5173`.

Useful checks:

```bash
npm test
npm run build
npm audit
```

## Stage 0 contract

- Login sends either `{"email", "password"}` or
  `{"nickname", "password"}`. The single identifier field selects email when
  it contains `@`.
- The backend returns access and refresh tokens as JSON. This demo keeps both
  in `sessionStorage`, sends the access token as a Bearer token, and performs
  one coordinated refresh attempt after a `401`.
- Logout calls `/auth/logout` when possible and always clears the browser
  session locally.
- Successful responses may use the backend's `{ "data": ... }` envelope.
  Errors use `{ "error": { "code", "message", "details" } }`.
- Ticket status, priority, category, tag, visibility, role, and analysis-status
  values in `src/api/types.ts` match the backend enums.
- Customers do not choose priority while creating a ticket. Priority remains a
  server-owned triage field.
- Customers do not choose a department or required agent skills. New tickets
  remain unassigned and await system classification or Manager+ triage.
- Controls are role- and state-aware. Search, My Queue, customer info, related
  issues, attachments, users, routing, settings, and notifications call real
  backend operations.

The demo session policy is intentionally simple. A production browser
application would normally keep the refresh token in a Secure, HttpOnly,
SameSite cookie, keep the access token short-lived and preferably in memory,
add CSRF protection where needed, and avoid making refresh credentials
available to JavaScript.

## Connected workflow

The implemented browser flow covers:

```text
login
  -> list/filter/sort/page tickets
  -> create a customer request without internal routing metadata
  -> view ticket, public/internal comments, and history
  -> Manager+ selects routing metadata and the routing worker may assign it
  -> perform allowed claim/assign/start/status actions
  -> request and poll durable AI analysis results
  -> inspect customer summary, related tickets, attachments, and notifications
  -> manage users/routing/settings for the permitted role
  -> logout
```

AI analysis requires an RQ worker on the `ticket_jobs` queue. Automatic routing
requires `ticket_routing`. The UI distinguishes HTTP/API errors from a
network-level unavailable API, and saved analysis results remain the durable
source of truth rather than the RQ job record.
