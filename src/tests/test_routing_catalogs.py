from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from src import constants, models
from src.db import models as db_models
from src.db import operations
from src.db.migrations import add_ticket_department_id, backfill_legacy_departments
from src.exceptions import (
    AgentDepartmentChangeConflictError,
    AuthorizationError,
    InactiveRoutingCatalogError,
    RoutingCatalogConflictError,
    TicketStatusConflictError,
)
from src.services import routing_catalogs
from src.services import tickets as ticket_service
from src.services import users as user_service


def _user(user_id: str, role: constants.Role, now: datetime) -> db_models.User:
    return db_models.User(
        id=user_id,
        nickname=user_id,
        avatar_url=None,
        first_name="Catalog",
        last_name="Manager",
        phone=f"+1555{len(user_id):07d}",
        email=f"{user_id}@example.com",
        role=role,
        password="hash",
        updated_at=now,
        created_at=now,
        deleted_at=None,
        user_status=constants.UserStatus.ACTIVE,
    )


def _database(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'catalogs.db'}")
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(operations, "engine", engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("manager", constants.Role.MANAGER, now),
                _user("customer", constants.Role.USER, now),
            ]
        )
    return engine


def test_manager_crud_archives_department_and_keeps_name_reserved(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")

    created = routing_catalogs.create_department(
        models.DepartmentCreate(name=" Support ", description="Main queue"),
        manager,
    )
    assert created.name == "Support"

    updated = routing_catalogs.update_department(
        created.id,
        models.DepartmentUpdate(description="Primary support queue"),
        manager,
    )
    assert updated.description == "Primary support queue"

    archived = routing_catalogs.archive_department(created.id, manager)
    assert archived.deleted_at is not None
    assert routing_catalogs.list_departments(manager) == []
    assert [item.id for item in routing_catalogs.list_departments(
        manager,
        include_archived=True,
    )] == [created.id]

    with pytest.raises(RoutingCatalogConflictError) as exc_info:
        routing_catalogs.create_department(
            models.DepartmentCreate(name="support"),
            manager,
        )
    assert exc_info.value.code == "routing_catalog_name_conflict"

    with Session(engine) as session:
        events = list(session.scalars(select(db_models.Event).order_by(db_models.Event.created_at)))
    assert [event.event_type for event in events] == [
        constants.EventType.DEPARTMENT_CREATED,
        constants.EventType.DEPARTMENT_UPDATED,
        constants.EventType.DEPARTMENT_ARCHIVED,
    ]


def test_department_migration_is_idempotent_and_preserves_legacy_profile_values(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy-routing.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tickets (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE agent_profiles "
            "(user_id VARCHAR(36) PRIMARY KEY, department_id VARCHAR(36))"
        )
        connection.exec_driver_sql(
            "INSERT INTO agent_profiles (user_id, department_id) "
            "VALUES ('agent', 'Support')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE departments ("
            "id VARCHAR(36) PRIMARY KEY, name VARCHAR(100) NOT NULL, "
            "normalized_name VARCHAR(100) NOT NULL UNIQUE, "
            "description VARCHAR(500), created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL, deleted_at DATETIME)"
        )

    add_ticket_department_id(engine)
    add_ticket_department_id(engine)
    backfill_legacy_departments(engine)
    backfill_legacy_departments(engine)

    assert "department_id" in {
        column["name"] for column in inspect(engine).get_columns("tickets")
    }
    with engine.connect() as connection:
        department = connection.exec_driver_sql(
            "SELECT id, normalized_name FROM departments"
        ).one()
    assert department == ("Support", "support")


def test_catalog_management_is_manager_only(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        customer = session.get(db_models.User, "customer")

    with pytest.raises(AuthorizationError):
        routing_catalogs.create_skill(models.SkillCreate(name="Python"), customer)


def test_skill_names_are_case_insensitive_and_customer_create_rejects_routing_fields(
    monkeypatch,
    tmp_path,
):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")

    routing_catalogs.create_skill(models.SkillCreate(name="Python"), manager)
    with pytest.raises(RoutingCatalogConflictError):
        routing_catalogs.create_skill(models.SkillCreate(name=" PYTHON "), manager)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        models.TicketCreate(
            title="Need Python help",
            description="The worker fails",
            category=constants.Category.AGENT_WORKFLOW,
            department_id="support",
        )


def test_customer_can_read_active_catalog_but_not_archived_catalog(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")
        customer = session.get(db_models.User, "customer")

    skill = routing_catalogs.create_skill(models.SkillCreate(name="Redis"), manager)
    assert [item.id for item in routing_catalogs.list_skills(customer)] == [skill.id]
    routing_catalogs.archive_skill(skill.id, manager)
    assert routing_catalogs.list_skills(customer) == []
    with pytest.raises(AuthorizationError):
        routing_catalogs.list_skills(customer, include_archived=True)


def test_manager_configures_agent_department_and_skills(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")
    department = routing_catalogs.create_department(
        models.DepartmentCreate(name="Support"),
        manager,
    )
    skill = routing_catalogs.create_skill(models.SkillCreate(name="Python"), manager)
    with Session(engine) as session, session.begin():
        session.add(_user("agent", constants.Role.AGENT, now))
        session.add(
            db_models.AgentProfile(
                user_id="agent",
                availability_status=constants.AvailabilityStatus.OFFLINE,
                availability_reason="profile_setup_required",
                availability_note=None,
                unavailable_until=None,
                max_active_tickets=0,
                last_assigned_at=None,
                department_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    monkeypatch.setattr(
        user_service,
        "dispatch_waiting_tickets_after_capacity_event",
        lambda *_: None,
    )

    response = user_service.update_agent_profile_settings(
        "agent",
        models.AgentProfileManagementUpdate(
            department_id=department.id,
            skill_ids=[skill.id],
            max_active_tickets=3,
        ),
        manager,
    )
    assert response.department_id == department.id
    assert response.skill_ids == [skill.id]

    routing_catalogs.archive_skill(skill.id, manager)
    with pytest.raises(InactiveRoutingCatalogError):
        user_service.update_agent_profile_settings(
            "agent",
            models.AgentProfileManagementUpdate(skill_ids=[skill.id]),
            manager,
        )


def test_agent_department_change_is_blocked_with_active_work(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")
    support = routing_catalogs.create_department(models.DepartmentCreate(name="Support"), manager)
    billing = routing_catalogs.create_department(models.DepartmentCreate(name="Billing"), manager)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                _user("agent", constants.Role.AGENT, now),
                db_models.AgentProfile(
                    user_id="agent",
                    availability_status=constants.AvailabilityStatus.AVAILABLE,
                    availability_reason=None,
                    availability_note=None,
                    unavailable_until=None,
                    max_active_tickets=2,
                    last_assigned_at=None,
                    department_id=support.id,
                    created_at=now,
                    updated_at=now,
                ),
                db_models.Ticket(
                    id="active-ticket",
                    title="Active",
                    description="Active assigned ticket",
                    category=constants.Category.ACCOUNT_ACCESS,
                    tags=None,
                    department_id=support.id,
                    assigned_agent_id="agent",
                    creator_user_id="customer",
                    status=constants.Status.IN_PROGRESS,
                    priority=constants.Priority.NORMAL,
                    updated_at=now,
                    created_at=now,
                    due_at=None,
                    deleted_at=None,
                ),
            ]
        )

    with pytest.raises(AgentDepartmentChangeConflictError):
        user_service.update_agent_profile_settings(
            "agent",
            models.AgentProfileManagementUpdate(department_id=billing.id),
            manager,
        )


def test_customer_ticket_creation_starts_without_routing_metadata(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        customer = session.get(db_models.User, "customer")

    ticket = ticket_service.create_ticket(
        models.TicketCreate(
            title="Redis timeout",
            description="The cache request times out",
            category=constants.Category.PERFORMANCE,
        ),
        customer,
    )
    assert ticket.department_id is None
    assert ticket.skill_ids == []
    assert ticket.status is constants.Status.NEW
    assert ticket.assigned_agent_id is None


def test_manager_can_set_routing_metadata_only_before_assignment(monkeypatch, tmp_path):
    engine = _database(monkeypatch, tmp_path)
    with Session(engine) as session:
        manager = session.get(db_models.User, "manager")
        customer = session.get(db_models.User, "customer")
    billing = routing_catalogs.create_department(models.DepartmentCreate(name="Billing"), manager)
    skill = routing_catalogs.create_skill(models.SkillCreate(name="Python"), manager)
    enqueued = []
    monkeypatch.setattr(
        ticket_service,
        "enqueue_ticket_routing_job",
        lambda ticket_id: enqueued.append(ticket_id),
    )
    monkeypatch.setattr(ticket_service, "delete_cached_ticket", lambda *_: True)
    ticket = ticket_service.create_ticket(
        models.TicketCreate(
            title="Needs triage",
            description="Please choose the routing metadata",
            category=constants.Category.ACCOUNT_ACCESS,
        ),
        customer,
    )

    updated = ticket_service.update_ticket(
        ticket.id,
        models.TicketUpdate(department_id=billing.id, skill_ids=[skill.id]),
        manager,
    )
    assert updated.department_id == billing.id
    assert updated.skill_ids == [skill.id]
    assert enqueued == [ticket.id]

    with Session(engine) as session, session.begin():
        stored = session.get(db_models.Ticket, ticket.id)
        stored.assigned_agent_id = "manager"
        stored.status = constants.Status.OPEN

    with pytest.raises(TicketStatusConflictError) as exc_info:
        ticket_service.update_ticket(
            ticket.id,
            models.TicketUpdate(skill_ids=[]),
            manager,
        )
    assert getattr(exc_info.value, "code", None) == "ticket_routing_metadata_locked"
