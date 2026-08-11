# Five-minute synthetic demo

Use a disposable local `.env` and synthetic data only. Never record a password,
refresh token, personal browser tabs, or a terminal containing secrets.

1. Run `./project.sh`; confirm `db`, `redis`, `api`, `worker`, `cron`, and
   `frontend` are healthy with `./project.sh status`.
2. Sign in using the locally configured superadmin from the password manager,
   then show All tickets, URL search/filter state, and the empty/loading/error
   states if useful.
3. Open a ticket, show Customer Info, Activity, Related Issues, and the
   ticket-scoped attachment selector using a synthetic `sample.txt`.
4. In a separate synthetic staff account, show My queue, claim/start work,
   add a public comment, and observe the notification bell's unread count.
5. Show Routing and My Settings, then sign out. End by showing the architecture
   diagram and `npm audit --omit=dev` result; do not show `.env` contents.

The GIF recording is intentionally left as a human-recorded artifact. The
sequence above is safe to follow without exposing credentials.

For a synthetic walkthrough dataset, provide a password only in the shell and
run the idempotent seed command. It never resets the database and does not
store the password in the repository:

```bash
DEMO_MODE=1 DEMO_PASSWORD='use-a-local-only-password' ./project.sh demo-data
```

The seed creates `demo-manager`, `demo-agent`, and `demo-customer` plus a
department, skill, two tickets, a comment, a related issue, a notification,
and a small text attachment. The configured superadmin remains the account
used for administration.
