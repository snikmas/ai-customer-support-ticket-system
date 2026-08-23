# Project TODO

Status: local portfolio/learning v1 closure in progress. Historical closure items remain checked; the provider-selection slice below is the active work.

## P0 — ResolveAI provider-selection closure

- [x] Add one PostgreSQL-backed global AI setting for `fake`, `openrouter`, or direct `deepseek`.
  - [x] Admin and Super Admin can read and update the provider/model; other roles are forbidden.
  - [x] Keep provider credentials in process environment configuration only.
  - [x] Validate fixed fake model, current DeepSeek Flash/Pro IDs, and bounded OpenRouter model IDs.
  - [x] Apply changes to new analyses without restarting services.
- [x] Snapshot provider, model, and prompt version before enqueue; preserve that snapshot for queued/running work.
- [x] Add an isolated provider-test action using a fixed synthetic snapshot; it must not change the active setting.
- [x] Record safe provider-setting and provider-test audit events without prompts, outputs, or credentials.
- [x] Add the direct DeepSeek adapter with JSON mode, bounded output, token accounting, retries, and safe error mapping.
- [x] Add Admin/Super Admin AI Settings UI with readiness, privacy note, loading, conflict, forbidden, and failure states.
- [x] Verify fake locally and direct DeepSeek live only with synthetic data under the approved aggregate US $0.10 limit.
- [x] Return the active provider to `fake` and update release documentation with precise privacy limits.
- [ ] OpenRouter live testing remains intentionally waived for this local closure; its adapter and automated tests remain covered.

## P1 — Complete before calling the portfolio version final

- [x] Fix the bare-metal setup instructions.
  - [x] Document `REDIS_URL=redis://localhost:6379/0` in `.env.example`.
  - [x] Make the documented backend test command explicitly use isolated Redis-disabled tests.
  - [x] Acceptance: the README test command passes without manually discovering missing Redis configuration.

- [x] Refresh `docs/ACCEPTANCE.md` against the current closure working tree.
  - [x] Replace the old acceptance wording and record the current backend/frontend test results.
  - [x] Record that Docker health, the frontend proxy, the API root, and the authentication error envelope were rechecked.

- [x] Clarify the AI verification boundary in the README.
  - [x] State that the deterministic fake analyzer is the default verified demo mode.
  - [x] State that OpenRouter has an adapter and automated tests, but the real provider path requires an external key and was not part of the local acceptance run.

## P2 — Recommended design and maintainability polish

- [x] Remove runtime service-signature introspection from `src/routers/users.py`.
  - [x] Give `get_all_users()` one stable interface and call it directly from the router.
  - [x] Acceptance: user-list filtering tests still pass and the router no longer inspects service implementation details.

- [x] Review and remove stale comments and naming leftovers.
  - [x] Remove the identified uncertain comments, typo, and unused comment-era variable.
  - Do not change behavior while doing this cleanup.

- [x] Add a narrowly scoped Python lint check to CI using Ruff (`E9` and `F821`).
  - Broader formatting cleanup remains intentionally separate from this closure pass.

## P3 — Deliberately deferred outside the local v1 scope

- [x] Keep local attachment storage until a second storage implementation is needed.
- [x] Keep local `.env` secrets for the private/local demo; use a managed secret store only for deployment.
- [x] Defer production metrics, traces, alerts, and rollout procedures.
- [x] Defer a full Compose end-to-end test in CI; local Compose acceptance is recorded above.
- [x] Do not deploy a public demo in this closure pass; revisit data-retention, authentication, and cost limits before deployment.

## Definition of done

- [x] P1 items are complete.
- [x] Backend and frontend tests pass.
- [x] Frontend production build passes.
- [x] Compose configuration and live health checks pass.
- [x] README and acceptance evidence match the current closure working tree.
- [x] The project is presented as a finished local portfolio v1, not as a production SaaS.
