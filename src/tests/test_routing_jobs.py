from types import SimpleNamespace

import pytest
from rq.job import validate_job_id
from sqlalchemy.exc import IntegrityError, OperationalError

from src import constants
from src.db.operations import TicketRoutingResult
from src.jobs import service as jobs_service
from src.jobs import tasks as job_tasks
from src.models import TicketCreate
from src.services import tickets as ticket_service


class FakeRoutingJob:
    def __init__(self, status="queued"):
        self.id = "route-ticket-ticket-1"
        self.status = status
        self.deleted = False

    def get_status(self, refresh=False):
        return self.status

    def delete(self):
        self.deleted = True


def test_enqueue_routing_job_uses_bounded_settings_retry_and_logging(
    monkeypatch,
    caplog,
):
    captured = {}
    job = FakeRoutingJob()

    class FakeQueue:
        def fetch_job(self, job_id):
            captured["fetched_job_id"] = job_id
            return None

        def enqueue(self, function, ticket_id, **settings):
            captured.update(
                function=function,
                ticket_id=ticket_id,
                settings=settings,
            )
            return job

    monkeypatch.setattr(
        jobs_service,
        "get_ticket_routing_queue",
        lambda: FakeQueue(),
    )
    caplog.set_level("INFO")

    result = jobs_service.enqueue_ticket_routing_job("ticket-1")

    retry = captured["settings"].pop("retry")
    assert captured == {
        "fetched_job_id": "route-ticket-ticket-1",
        "function": job_tasks.route_ticket,
        "ticket_id": "ticket-1",
        "settings": {
            "job_id": "route-ticket-ticket-1",
            "unique": True,
            "job_timeout": 60,
            "result_ttl": 600,
            "failure_ttl": 3600,
        },
    }
    assert retry.max == 2
    assert retry.intervals == [10, 30]
    assert result is job
    assert "Ticket routing job enqueued" in caplog.text


def test_routing_job_id_is_accepted_by_real_rq_validator():
    job_id = jobs_service._routing_job_id(
        "e349ea85-51ef-4928-904d-0d8c93a22720"
    )

    validate_job_id(job_id)

    assert job_id == "route-ticket-e349ea85-51ef-4928-904d-0d8c93a22720"


@pytest.mark.parametrize(
    "active_status",
    ["created", "queued", "started", "deferred", "scheduled"],
)
def test_enqueue_routing_job_reuses_an_active_job(
    monkeypatch,
    active_status,
):
    existing = FakeRoutingJob(status=active_status)
    queue = SimpleNamespace(
        fetch_job=lambda _: existing,
        enqueue=lambda *_args, **_kwargs: pytest.fail(
            "an active routing job must not be duplicated"
        ),
    )
    monkeypatch.setattr(
        jobs_service,
        "get_ticket_routing_queue",
        lambda: queue,
    )

    assert jobs_service.enqueue_ticket_routing_job("ticket-1") is existing
    assert existing.deleted is False


def test_enqueue_routing_job_replaces_a_terminal_job(monkeypatch):
    existing = FakeRoutingJob(status="finished")
    replacement = FakeRoutingJob(status="queued")

    class FakeQueue:
        def fetch_job(self, _):
            return existing

        def enqueue(self, *_args, **_settings):
            assert existing.deleted is True
            return replacement

    monkeypatch.setattr(
        jobs_service,
        "get_ticket_routing_queue",
        lambda: FakeQueue(),
    )

    assert jobs_service.enqueue_ticket_routing_job("ticket-1") is replacement


@pytest.mark.parametrize(
    "outcome",
    [
        constants.TicketRoutingOutcome.NO_ELIGIBLE_AGENT,
        constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE,
    ],
)
def test_route_ticket_returns_terminal_domain_outcomes_without_retry_errors(
    monkeypatch,
    outcome,
):
    monkeypatch.setattr(
        job_tasks,
        "try_route_ticket",
        lambda ticket_id: TicketRoutingResult(
            outcome=outcome,
            ticket_id=ticket_id,
        ),
    )
    monkeypatch.setattr(
        job_tasks,
        "delete_cached_ticket",
        lambda _: pytest.fail("a no-op routing result must not touch the cache"),
    )

    assert job_tasks.route_ticket("ticket-1") == {
        "outcome": outcome.value,
        "ticket_id": "ticket-1",
        "assigned_agent_id": None,
    }


def test_route_ticket_invalidates_cache_only_after_assignment(monkeypatch):
    invalidated = []
    monkeypatch.setattr(
        job_tasks,
        "try_route_ticket",
        lambda ticket_id: TicketRoutingResult(
            outcome=constants.TicketRoutingOutcome.ASSIGNED,
            ticket_id=ticket_id,
            assigned_agent_id="agent-1",
        ),
    )
    monkeypatch.setattr(
        job_tasks,
        "delete_cached_ticket",
        lambda ticket_id: invalidated.append(ticket_id) or True,
    )

    result = job_tasks.route_ticket("ticket-1")

    assert result["outcome"] == constants.TicketRoutingOutcome.ASSIGNED.value
    assert result["assigned_agent_id"] == "agent-1"
    assert invalidated == ["ticket-1"]


def test_route_ticket_keeps_retry_budget_for_temporary_database_failure(
    monkeypatch,
):
    current_job = SimpleNamespace(
        retries_left=2,
        save=lambda: pytest.fail("temporary failure must keep its retry budget"),
    )
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)
    monkeypatch.setattr(
        job_tasks,
        "try_route_ticket",
        lambda _: (_ for _ in ()).throw(
            OperationalError("UPDATE tickets", {}, ConnectionError())
        ),
    )

    with pytest.raises(OperationalError):
        job_tasks.route_ticket("ticket-1")

    assert current_job.retries_left == 2


def test_route_ticket_disables_retry_for_non_temporary_failure(monkeypatch):
    saved = []
    current_job = SimpleNamespace(
        retries_left=2,
        save=lambda: saved.append(True),
    )
    monkeypatch.setattr(job_tasks, "get_current_job", lambda: current_job)
    monkeypatch.setattr(
        job_tasks,
        "try_route_ticket",
        lambda _: (_ for _ in ()).throw(
            IntegrityError("INSERT event", {}, ValueError("duplicate"))
        ),
    )

    with pytest.raises(IntegrityError):
        job_tasks.route_ticket("ticket-1")

    assert current_job.retries_left == 0
    assert saved == [True]


def test_duplicate_task_execution_relies_on_atomic_operation_and_invalidates_once(
    monkeypatch,
):
    outcomes = iter(
        [
            TicketRoutingResult(
                outcome=constants.TicketRoutingOutcome.ASSIGNED,
                ticket_id="ticket-1",
                assigned_agent_id="agent-1",
            ),
            TicketRoutingResult(
                outcome=constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE,
                ticket_id="ticket-1",
            ),
        ]
    )
    invalidated = []
    monkeypatch.setattr(job_tasks, "try_route_ticket", lambda _: next(outcomes))
    monkeypatch.setattr(
        job_tasks,
        "delete_cached_ticket",
        lambda ticket_id: invalidated.append(ticket_id) or True,
    )

    first = job_tasks.route_ticket("ticket-1")
    second = job_tasks.route_ticket("ticket-1")

    assert first["outcome"] == constants.TicketRoutingOutcome.ASSIGNED.value
    assert second["outcome"] == (
        constants.TicketRoutingOutcome.TICKET_NOT_ROUTABLE.value
    )
    assert invalidated == ["ticket-1"]


def test_create_ticket_preserves_committed_ticket_when_enqueue_fails(
    monkeypatch,
    make_user,
    make_ticket,
    caplog,
):
    requester = make_user(id="customer")
    stored_ticket = make_ticket(
        id="ticket-1",
        creator_user_id=requester.id,
        tags=[constants.Tag.API_KEY],
    )
    monkeypatch.setattr(
        ticket_service.operations,
        "create_ticket",
        lambda ticket, event: stored_ticket,
    )
    monkeypatch.setattr(
        ticket_service,
        "enqueue_ticket_routing_job",
        lambda _: (_ for _ in ()).throw(ConnectionError("Redis unavailable")),
    )
    caplog.set_level("ERROR")

    result = ticket_service.create_ticket(
        TicketCreate(
            title="Cannot authenticate",
            description="My API key is rejected by the service.",
            category=constants.Category.ACCOUNT_ACCESS,
            tags=[constants.Tag.API_KEY],
        ),
        requester,
    )

    assert result.id == "ticket-1"
    assert result.status is constants.Status.NEW
    assert result.assigned_agent_id is None
    assert "Ticket routing enqueue failed after ticket creation" in caplog.text


def test_create_ticket_enqueues_only_after_database_create_returns(
    monkeypatch,
    make_user,
    make_ticket,
):
    requester = make_user(id="customer")
    stored_ticket = make_ticket(
        id="ticket-1",
        creator_user_id=requester.id,
        tags=[constants.Tag.API_KEY],
    )
    call_order = []

    def fake_database_create(ticket, event):
        call_order.append(("committed", ticket.status, ticket.assigned_agent_id))
        return stored_ticket

    def fake_enqueue(ticket_id):
        call_order.append(("enqueued", ticket_id))
        return SimpleNamespace(id=f"route-ticket-{ticket_id}")

    monkeypatch.setattr(
        ticket_service.operations,
        "create_ticket",
        fake_database_create,
    )
    monkeypatch.setattr(
        ticket_service,
        "enqueue_ticket_routing_job",
        fake_enqueue,
    )

    result = ticket_service.create_ticket(
        TicketCreate(
            title="Cannot authenticate",
            description="My API key is rejected by the service.",
            category=constants.Category.ACCOUNT_ACCESS,
            tags=[constants.Tag.API_KEY],
        ),
        requester,
    )

    assert result.id == "ticket-1"
    assert call_order == [
        ("committed", constants.Status.NEW, None),
        ("enqueued", "ticket-1"),
    ]
