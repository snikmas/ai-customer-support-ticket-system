# Interview demo and operator handoff

**For Mary · 30 September 2026**

Use this runbook after reading [ARCHITECTURE.md](ARCHITECTURE.md). The current checks and remaining risks are in [INTERVIEW_CHECK.md](INTERVIEW_CHECK.md).

## Prepare tonight

1. Start the normal application with `./project.sh` from the repository root. Keep the existing configuration, keys, and volumes.
2. Open `http://localhost:5173` and sign in with your existing demo account. The automated browser rehearsal used separate synthetic accounts; your ordinary login remains your own acceptance check.
3. Choose an existing synthetic ticket or create one clearly labeled “Interview demo.” Keep real customer information out of the presentation.
4. Verify that your agent has an active department, suitable skills, positive capacity, and Available status. The API supports profile management more fully than the Users page. Prepare these fields before the interview.
5. Choose the provider you intend to show. The fake provider proves the local workflow without a paid call. If you intend to show DeepSeek or OpenRouter, run **Test provider** with authorized synthetic content before the interview. Test and Save selection are separate actions.
6. Rehearse the sequence below once. Note the ticket ID and the roles you will use. Do not save passwords or tokens in these notes.

Do not regenerate existing JWT keys, reset the database, or remove volumes to prepare the demo. If the system already has data, keep it.

## A six-minute demonstration

| Approximate time | Show | Explain |
|---|---|---|
| 0:00–1:00 | Ticket list with search/filter. | The backend filters and paginates SQL records according to the current user. |
| 1:00–2:00 | Synthetic ticket detail and routing. | Customer, assignee, department, skills, priority, status, and deadline are different concepts. |
| 2:00–3:00 | Agent Start work / permitted transition. | Assignment creates Open; a person explicitly starts work. Changes produce audit events. |
| 3:00–4:00 | Public reply, internal note, small file. | Ticket access and comment visibility are checked separately; files are not public static URLs. |
| 4:00–5:00 | Completed analysis. | The API accepts work, Redis queues it, the worker runs the adapter, SQL keeps the result, and the browser polls. Label fake output accurately. |
| 5:00–6:00 | History and one engineering tradeoff. | Explain a tested bug/fix, then a limitation such as stale Running recovery after a hard worker kill. |

Use separate browser sessions/tabs as appropriate for roles, and verify which account is currently signed in before an action. Some tokens are scoped to a tab session. Do not display developer storage or Authorization headers during the interview.

If a provider fails, show the safe failure state and explain the lifecycle. Do not repeatedly click analysis while an active result is already pending.

## Operator handoff: prove the complete request path is ready

### Objective

Distinguish “the frontend page opens” from “the API is reachable through the frontend and the worker can execute background work.” Collect enough evidence to explain which boundary failed if either claim is false.

This mission is connected to two failures found in the rehearsal: the API was stopped while the frontend was still serving HTML, and later Nginx retained an old API container address after recreation.

### Understand the runtime path first

```text
browser
  -> host port 5173
  -> frontend container / Nginx
  -> Docker DNS lookup for api
  -> API container socket on 8000
  -> Uvicorn process
  -> FastAPI handler
  -> PostgreSQL and Redis

analysis request additionally:
  -> Redis ticket_jobs queue
  -> RQ worker parent process
  -> job child process
  -> analyzer
  -> SQL analysis result
  -> browser polling request
```

A TCP socket is a connection boundary. DNS maps a service name to an address. A process runs the code behind the socket. HTTP tells you how the application handled a request. You can have success at one boundary and failure at the next.

The frontend container can serve `index.html` without the API. Nginx can therefore return `200` for `/` and `502` for `/api/health`. Direct API health at port 8000 helps separate an API failure from a proxy/network failure.

Containers have independent network identities. Recreating the API may give it a new IP while its Compose service name remains `api`. The proxy now resolves that name periodically through Docker DNS. Recovery is bounded by resolution and startup timing; it is not instantaneous zero-downtime deployment. See [Nginx dynamic upstream resolution](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server).

A worker is a separate process. Health checks can show PostgreSQL/Redis up while nobody consumes the queue. On Linux, the RQ worker can spawn job children and a scheduler child. Parent/child evidence helps distinguish a waiting worker from an executing job and from the delayed retry scheduler.

### Failure modes and distinguishing evidence

| Symptom | Likely boundary | Evidence to check |
|---|---|---|
| Connection refused / curl exit 7 | No reachable listener or service path. | Container state and host listening ports. |
| curl exit 28 | Request exceeded timeout. | Connection/application/dependency delay; compare direct API and proxy. |
| Frontend `/` is 200; proxy health is 502 | Nginx could not reach/use its API upstream. | Direct API health, API state, proxy DNS/configuration. |
| Direct API `/health` is 503 | API responds but a required dependency is unhealthy. | Health JSON database/Redis fields. |
| Both health paths are 200; analysis remains Pending | Queue consumption or execution not ready. | Worker registration, queue depth, scheduler/process state, result lifecycle. |
| Analysis Running persists after worker death | Execution state and durable SQL disagree. | Known remaining recovery gap; do not claim a restart repairs it. |
| API is Exited (0) | The long-running server stopped cleanly. | It is still unavailable despite the zero exit code. |
| Migration is Exited (0) | One-shot schema task completed. | This is the expected migration lifecycle. |

An HTTP code `000` printed by curl means no HTTP response was obtained; it is not an actual HTTP status sent by the server. With `--fail`, HTTP errors also cause a nonzero curl exit code. Check both HTTP status and process exit status when diagnosing.

### Safe starting conditions

Use the normal existing Docker application. The mission is read-only apart from submitting one synthetic analysis through the normal UI. Do not stop the database, kill real workers, remove containers/volumes, or inject failures into normal data.

Choose the command order yourself after stating what you predict. Start with broad state, then compare request paths, then examine the queue/worker boundary. If you find a failure, preserve evidence before any restart.

### Command toolkit

Run these from the repository root. Container names below match the current `internship_project` Compose project.

```bash
./project.sh status
ss -ltnp '( sport = :5173 or sport = :8000 )'
```

`status` reports lifecycle and health. `ss -ltnp` shows listening TCP sockets, numeric addresses/ports, and process information when permitted. `0.0.0.0` means all IPv4 interfaces; `127.0.0.1` means loopback. A listener proves only that a connection can be accepted on that path.

Compare direct and proxied health:

```bash
curl --noproxy '*' --fail --silent --show-error --max-time 3 http://127.0.0.1:8000/health
curl --noproxy '*' --fail --silent --show-error --max-time 3 http://127.0.0.1:5173/api/health
```

`--noproxy '*'` prevents your local proxy settings from changing the route being diagnosed. `--max-time 3` bounds the wait. Look for HTTP success and `database: up`, `redis: up`. These requests use no authentication secrets.

Inspect lifecycle and processes:

```bash
docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}}' internship_project-api-1 internship_project-migrate-1
docker top internship_project-worker-1 -eo pid,ppid,comm
docker inspect --format '{{json .Config.Cmd}}' internship_project-worker-1
```

The API should run; the migration should have exited successfully. In `docker top`, PID identifies a process and PPID identifies its parent. `comm` shows executable names without dumping environment variables. The worker command should include both queues and `--with-scheduler`. A startup flag alone does not prove scheduler ownership; it is one piece of evidence.

Check worker registration and queue depth:

```bash
docker exec internship_project-worker-1 rq info --url redis://redis:6379/0
docker exec internship_project-redis-1 redis-cli LLEN rq:queue:ticket_jobs
```

`rq info` reports workers and queue state. `LLEN` reports waiting entries, not already running or scheduled jobs. A zero waiting count can mean either no work or work already taken; combine it with the analysis result and worker evidence. The SQL analysis record remains the final product evidence.

Do not inspect full container environment, private configuration, key files, browser token storage, or raw Redis job payloads for this mission. If you need logs after a failure, inspect a narrow time/component scope locally and remove private data before sharing an excerpt.

### Evidence to collect

Record:

- API/frontend/worker lifecycle and database/Redis health.
- Listening host ports and bind addresses.
- Direct and proxied health results.
- Worker registration, queue count before/after, and parent/child observations.
- One synthetic analysis ID, selected provider label, and final status/attempt count. Never record a token.

Queue depth can change too quickly to observe every intermediate state. If so, say that and use the durable completed result and worker registration rather than inventing a missing observation.

### Success condition

Both health paths succeed, the worker is registered for the intended queues, and one synthetic analysis progresses to its expected terminal result. You can explain why these are three different claims and identify which command would distinguish a proxy failure from a worker failure.

Your mission remains **pending** until you perform it and explain the evidence. Automated checks already completed by the assistant do not count as your demonstrated operator skill.

### Finish with a 60-second incident explanation

Use your own words:

> The symptom was … . I first predicted … . The direct API check showed …, while the proxy check showed … . Container/socket/worker evidence showed … . That places the problem at … because … . I changed nothing until … . The final evidence is … . The remaining uncertainty is … .

If everything works, explain the two rehearsal incidents using your current healthy evidence and the report. Do not create an outage in normal services just to produce an incident.

### How a production team handles this concern

A service manager or orchestrator owns restart and graceful shutdown. Readiness checks cover useful dependency/service boundaries. Teams monitor proxy error rates, worker heartbeats, queue age, execution failures, and stuck durable jobs. Safe structured logs connect a request ID, ticket ID, and job/result ID without exposing credentials or customer text. Deployment checks verify traffic through the real ingress path, not only direct container health. Runbooks and incident reviews preserve the reasoning that led to a fix.

This repository has Compose restart policies, health endpoints, queues, and audit records. It does not yet have that complete production monitoring and recovery system.
