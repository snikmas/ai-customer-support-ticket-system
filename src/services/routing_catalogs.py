import unicodedata
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from src import constants
from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.exceptions import (
    AlreadyDeletedError,
    AuthorizationError,
    EmptyUpdateError,
    RoutingCatalogConflictError,
    RoutingCatalogNotFoundError,
)


CATALOG_MANAGER_ROLES = {
    constants.Role.MANAGER,
    constants.Role.ADMIN,
    constants.Role.SUPER_ADMIN,
}


def normalize_catalog_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def _require_manager(requester: api_models.User) -> None:
    if requester.role not in CATALOG_MANAGER_ROLES:
        raise AuthorizationError()


def _event(
    *,
    requester: api_models.User,
    entity_type: constants.EntityType,
    entity_id: str,
    event_type: constants.EventType,
    old_value: dict | None,
    new_value: dict,
    now: datetime,
) -> api_models.Event:
    return api_models.Event(
        id=constants.generate_id(),
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=requester.id,
        event_type=event_type,
        old_value=(constants._audit_json(old_value) if old_value is not None else None),
        new_value=constants._audit_json(new_value),
        metadata=None,
        created_at=now,
    )


def _create(model, data, requester, entity_type, event_type):
    _require_manager(requester)
    now = datetime.now(timezone.utc)
    record = model(
        id=constants.generate_id(),
        name=data.name,
        normalized_name=normalize_catalog_name(data.name),
        description=data.description,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    event = _event(
        requester=requester,
        entity_type=entity_type,
        entity_id=record.id,
        event_type=event_type,
        old_value=None,
        new_value={"name": record.name, "description": record.description},
        now=now,
    )
    try:
        return operations.create_routing_catalog_record(record, event)
    except IntegrityError as exc:
        raise RoutingCatalogConflictError(
            "That routing catalog name is already reserved",
            code="routing_catalog_name_conflict",
        ) from exc


def _list(model, requester, *, include_archived: bool):
    if include_archived:
        _require_manager(requester)
    return operations.list_routing_catalog_records(
        model,
        include_archived=include_archived,
    )


def _update(model, record_id, data, requester, entity_type, event_type):
    _require_manager(requester)
    record = operations.get_routing_catalog_record(model, record_id, include_archived=True)
    if record is None:
        raise RoutingCatalogNotFoundError()
    if record.deleted_at is not None:
        raise AlreadyDeletedError("Routing catalog record is archived")

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyUpdateError()
    old_value = {field: getattr(record, field) for field in changes}
    if "name" in changes:
        changes["normalized_name"] = normalize_catalog_name(changes["name"])
    now = datetime.now(timezone.utc)
    changes["updated_at"] = now
    event = _event(
        requester=requester,
        entity_type=entity_type,
        entity_id=record_id,
        event_type=event_type,
        old_value=old_value,
        new_value={field: value for field, value in changes.items() if field != "normalized_name"},
        now=now,
    )
    try:
        return operations.update_routing_catalog_record(model, record_id, changes, event)
    except IntegrityError as exc:
        raise RoutingCatalogConflictError(
            "That routing catalog name is already reserved",
            code="routing_catalog_name_conflict",
        ) from exc


def _archive(model, record_id, requester, entity_type, event_type):
    _require_manager(requester)
    record = operations.get_routing_catalog_record(model, record_id, include_archived=True)
    if record is None:
        raise RoutingCatalogNotFoundError()
    if record.deleted_at is not None:
        raise AlreadyDeletedError("Routing catalog record is already archived")
    now = datetime.now(timezone.utc)
    event = _event(
        requester=requester,
        entity_type=entity_type,
        entity_id=record_id,
        event_type=event_type,
        old_value={"deleted_at": None},
        new_value={"deleted_at": now},
        now=now,
    )
    return operations.update_routing_catalog_record(
        model,
        record_id,
        {"deleted_at": now, "updated_at": now},
        event,
    )


def create_department(data: api_models.DepartmentCreate, requester: api_models.User):
    return _create(
        db_models.Department,
        data,
        requester,
        constants.EntityType.DEPARTMENT,
        constants.EventType.DEPARTMENT_CREATED,
    )


def list_departments(requester: api_models.User, *, include_archived: bool = False):
    return _list(db_models.Department, requester, include_archived=include_archived)


def update_department(record_id: str, data: api_models.DepartmentUpdate, requester: api_models.User):
    return _update(
        db_models.Department,
        record_id,
        data,
        requester,
        constants.EntityType.DEPARTMENT,
        constants.EventType.DEPARTMENT_UPDATED,
    )


def archive_department(record_id: str, requester: api_models.User):
    return _archive(
        db_models.Department,
        record_id,
        requester,
        constants.EntityType.DEPARTMENT,
        constants.EventType.DEPARTMENT_ARCHIVED,
    )


def create_skill(data: api_models.SkillCreate, requester: api_models.User):
    return _create(
        db_models.Skill,
        data,
        requester,
        constants.EntityType.SKILL,
        constants.EventType.SKILL_CREATED,
    )


def list_skills(requester: api_models.User, *, include_archived: bool = False):
    return _list(db_models.Skill, requester, include_archived=include_archived)


def update_skill(record_id: str, data: api_models.SkillUpdate, requester: api_models.User):
    return _update(
        db_models.Skill,
        record_id,
        data,
        requester,
        constants.EntityType.SKILL,
        constants.EventType.SKILL_UPDATED,
    )


def archive_skill(record_id: str, requester: api_models.User):
    return _archive(
        db_models.Skill,
        record_id,
        requester,
        constants.EntityType.SKILL,
        constants.EventType.SKILL_ARCHIVED,
    )
