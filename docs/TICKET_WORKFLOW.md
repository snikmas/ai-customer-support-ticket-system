# Ticket workflow

The status graph is:

```text
NEW -> OPEN -> IN_PROGRESS -> PENDING -> IN_PROGRESS
                         |-> ON_HOLD -> IN_PROGRESS
                         |-> RESOLVED -> CLOSED -> REOPENED -> IN_PROGRESS
```

New tickets are created without department or assignee. Manager+ triage can
select active routing catalogs. An agent can claim an eligible New ticket;
assignment moves work to Open, and only the assigned agent can use Start work.

SLA deadlines are recalculated for status/priority transitions. RQ routing is
idempotent and uses department, skills, availability, and capacity. If no
eligible agent exists, the ticket remains safely unassigned for reconciliation.

Search supports exact ID and text matching across title/description plus
department, assignee, category, tag, status, priority, overdue, sort, and
pagination parameters. Visibility predicates are part of the SQL query before
the page slice is taken.
