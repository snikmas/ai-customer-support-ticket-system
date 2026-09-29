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

Availability and capacity are enforced wherever an agent takes work for
themselves: automatic routing and self-service claiming both reject agents who
are not `AVAILABLE` or who already hold `max_active_tickets` active tickets.
Manual assignment by a manager or admin (the assign endpoint and the
`assigned_agent_id` PATCH) is an intentional override: it bypasses availability
and capacity so managers can force-assign during escalations or rebalancing,
and it never unassigns existing work when capacity is later lowered.

Search supports exact ID and text matching across title/description plus
department, assignee, category, tag, status, priority, overdue, sort, and
pagination parameters. Visibility predicates are part of the SQL query before
the page slice is taken.
