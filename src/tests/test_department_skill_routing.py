from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src import constants
from src.db import models as db_models
from src.db import operations


def _catalog(model, record_id: str, now: datetime, *, archived: bool = False):
    return model(
        id=record_id,
        name=record_id.replace("-", " ").title(),
        normalized_name=record_id,
        description=None,
        created_at=now,
        updated_at=now,
        deleted_at=now if archived else None,
    )


def _user(user_id: str, role: constants.Role, now: datetime):
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="Routing",
        last_name="Test",
        phone=f"phone-{user_id}",
        email=f"{user_id}@example.com",
        role=role,
        password="hash",
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _profile(user_id: str, department_id: str, now: datetime, skills):
    return db_models.AgentProfile(
        user_id=user_id,
        availability_status=constants.AvailabilityStatus.AVAILABLE,
        availability_reason=None,
        availability_note=None,
        unavailable_until=None,
        max_active_tickets=5,
        last_assigned_at=None,
        department_id=department_id,
        created_at=now,
        updated_at=now,
        skills=list(skills),
    )


def _ticket(ticket_id: str, now: datetime, department_id: str, skills):
    return db_models.Ticket(
        id=ticket_id,
        title="Routing request",
        description="Needs specialist help",
        category=constants.Category.AGENT_WORKFLOW,
        tags=None,
        department_id=department_id,
        assigned_agent_id=None,
        creator_user_id="customer",
        status=constants.Status.NEW,
        priority=constants.Priority.NORMAL,
        updated_at=now,
        created_at=now,
        due_at=constants.calculate_sla_due_at(constants.Status.NEW, now),
        deleted_at=None,
        requested_skills=list(skills),
    )


def _database(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'department-skill-routing.db'}",
        connect_args={"timeout": 10},
    )
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    return engine


def _seed(monkeypatch, tmp_path, agent_specs, requested_skill_ids, *, ticket_department="support"):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    support = _catalog(db_models.Department, "support", now)
    billing = _catalog(db_models.Department, "billing", now)
    python = _catalog(db_models.Skill, "python", now)
    redis = _catalog(db_models.Skill, "redis", now)
    skills = {skill.id: skill for skill in [python, redis]}
    with Session(engine) as session, session.begin():
        session.add_all([support, billing, python, redis])
        session.add(_user("customer", constants.Role.USER, now))
        for user_id, department_id, skill_ids in agent_specs:
            session.add(_user(user_id, constants.Role.AGENT, now))
            session.add(
                _profile(
                    user_id,
                    department_id,
                    now,
                    [skills[skill_id] for skill_id in skill_ids],
                )
            )
        session.add(
            _ticket(
                "ticket",
                now,
                ticket_department,
                [skills[skill_id] for skill_id in requested_skill_ids],
            )
        )
    return engine


def test_exact_skill_match_wins_before_existing_workload_order(monkeypatch, tmp_path):
    engine = _seed(
        monkeypatch,
        tmp_path,
        [
            ("exact", "support", ["python", "redis"]),
            ("partial", "support", ["python"]),
        ],
        ["python", "redis"],
    )
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add(
            _ticket("exact-workload", now, "support", [])
        )
        session.get(db_models.Ticket, "exact-workload").assigned_agent_id = "exact"
        session.get(db_models.Ticket, "exact-workload").status = constants.Status.OPEN

    result = operations.try_route_ticket("ticket")
    assert result.assigned_agent_id == "exact"


def test_partial_match_wins_but_zero_match_remains_fallback(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [
            ("no-match", "support", []),
            ("partial", "support", ["python"]),
        ],
        ["python", "redis"],
    )
    assert operations.try_route_ticket("ticket").assigned_agent_id == "partial"


def test_exact_match_at_capacity_is_excluded(monkeypatch, tmp_path):
    engine = _seed(
        monkeypatch,
        tmp_path,
        [
            ("exact-at-capacity", "support", ["python", "redis"]),
            ("partial", "support", ["python"]),
        ],
        ["python", "redis"],
    )
    with Session(engine) as session, session.begin():
        session.get(
            db_models.AgentProfile,
            "exact-at-capacity",
        ).max_active_tickets = 0

    assert operations.try_route_ticket("ticket").assigned_agent_id == "partial"


def test_no_skill_match_still_assigns_same_department_fallback(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [("fallback", "support", [])],
        ["python"],
    )
    result = operations.try_route_ticket("ticket")
    assert result.outcome is constants.TicketRoutingOutcome.ASSIGNED
    assert result.assigned_agent_id == "fallback"


def test_other_department_is_never_used_as_fallback(monkeypatch, tmp_path):
    _seed(
        monkeypatch,
        tmp_path,
        [("billing-agent", "billing", ["python", "redis"])],
        ["python"],
    )
    result = operations.try_route_ticket("ticket")
    assert result.outcome is constants.TicketRoutingOutcome.NO_ELIGIBLE_AGENT
    assert result.assigned_agent_id is None
