# Ticket analysis lifecycle

## Sub-features

- Request one summary-only analysis for a ticket.
- Observe queued/running/completed or safe failed lifecycle.

## How to get to it (user POV)

Log in as an authorized synthetic staff user, open a ticket, and choose the
analysis action.

## Driving it with browser

Use the ticket detail action, wait for the result state, then query the
authenticated analysis-result endpoint to compare visible status with the
durable row.

## Gotchas

The worker and Redis must be healthy. A provider change must not rewrite a
previous result's provenance, and a provider failure must not silently fall
back.
