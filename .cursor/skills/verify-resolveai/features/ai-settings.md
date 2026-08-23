# AI settings and provider provenance

## Sub-features

- Admin/Super Admin global provider/model selection.
- Safe provider test using synthetic data.
- Immutable analysis provenance after enqueue.

## How to get to it (user POV)

Log in as Admin or Super Admin and open AI settings from the staff navigation.

## Driving it with browser

Read the current provider/model, save a valid choice, refresh, run the provider
test, and create an analysis. Repeat as Manager and Agent to verify forbidden
behavior. Record setting version, test outcome, and analysis provider/model
through safe API responses.

## Gotchas

Keys are environment-only and never appear in the page, API, database, logs,
or evidence. Direct external verification uses synthetic content only and is
stopped before the approved aggregate spending limit is exceeded.
