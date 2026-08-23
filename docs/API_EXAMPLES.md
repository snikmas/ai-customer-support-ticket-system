# API examples

All authenticated examples use `Authorization: Bearer $ACCESS_TOKEN`. JSON
success responses use `{ "data": ... }`; domain and validation failures use
`{ "error": { "code", "message", "details" } }`.

```bash
curl -G http://localhost:8000/tickets/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode 'search=timeout' \
  --data-urlencode 'assigned_to_me=true' \
  --data-urlencode 'limit=20'

curl http://localhost:8000/tickets/$TICKET_ID/customer \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -F 'file=@synthetic.txt;type=text/plain' \
  http://localhost:8000/tickets/$TICKET_ID/comments/$COMMENT_ID/attachments \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl http://localhost:8000/notifications/unread-count \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl http://localhost:8000/ai-settings/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -X PATCH http://localhost:8000/ai-settings/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","model":"deepseek-v4-flash","expected_version":1}'

curl -X POST http://localhost:8000/ai-settings/test \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","model":"deterministic-fake-v1"}'
```

AI settings are restricted to Admin and Super Admin. The provider test uses a
fixed synthetic snapshot and does not change the active selection. Keys remain
server-side environment configuration and are never returned by these routes.

Attachment policy is 5 MiB per file, five files per comment, and PDF/PNG/JPEG/
TXT/CSV/JSON only. Downloads re-check ticket and comment visibility.
