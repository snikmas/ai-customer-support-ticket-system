from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src import constants
from src.db import operations
from src.db.models import Base, Event, Ticket, User
from src.exceptions import AuthorizationError, ConflictError
from src.models import AIProviderTestRequest, AISettingsUpdate
from src.services import ai_settings
from src.services import analysis_results
from src.jobs import service as jobs_service
from src.analyzers import build_analyzer
from src.core import config


@pytest.fixture
def ai_engine(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'ai-settings.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(User(
            id="admin-1",
            nickname="admin",
            avatar_url=None,
            first_name="Admin",
            last_name="User",
            phone="admin-phone",
            email="admin@example.com",
            role=constants.Role.ADMIN,
            password="hashed",
            updated_at=now,
            created_at=now,
            deleted_at=None,
            user_status=constants.UserStatus.ACTIVE,
        ))
        session.commit()
    monkeypatch.setattr(operations, "engine", engine)
    yield engine
    engine.dispose()


def requester(role=constants.Role.ADMIN):
    return SimpleNamespace(id="admin-1", role=role)


def test_read_update_and_optimistic_conflict(ai_engine):
    initial = ai_settings.get_settings(requester())
    assert initial.provider == "fake"
    assert initial.model == "deterministic-fake-v1"
    assert initial.version == 1
    assert {item.provider for item in initial.providers} == {
        "fake",
        "openrouter",
        "deepseek",
    }

    updated = ai_settings.update_settings(
        AISettingsUpdate(
            provider="openrouter",
            model="openai/gpt-oss-20b",
            expected_version=1,
        ),
        requester(),
    )
    assert updated.provider == "openrouter"
    assert updated.version == 2

    with pytest.raises(ConflictError) as caught:
        ai_settings.update_settings(
            AISettingsUpdate(
                provider="fake",
                model="deterministic-fake-v1",
                expected_version=1,
            ),
            requester(),
        )
    assert caught.value.code == "ai_settings_conflict"
    assert operations.get_ai_setting().provider == "openrouter"

    with Session(ai_engine) as session:
        events = list(session.scalars(select(Event)).all())
    assert len(events) == 1
    assert events[0].event_type is constants.EventType.AI_SETTINGS_UPDATED
    assert "key" not in (events[0].new_value or "").lower()


def test_provider_test_is_fake_and_does_not_change_setting(ai_engine):
    before = operations.get_ai_setting()
    result = ai_settings.test_provider(
        AIProviderTestRequest(provider="fake", model="deterministic-fake-v1"),
        requester(),
    )
    after = operations.get_ai_setting()

    assert result.ok is True
    assert result.safe_error_code is None
    assert (after.provider, after.model, after.version) == (
        before.provider,
        before.model,
        before.version,
    )
    with Session(ai_engine) as session:
        events = list(session.scalars(select(Event)).all())
    assert events[0].event_type is constants.EventType.AI_PROVIDER_TESTED


def test_new_analysis_snapshots_current_selection_only(ai_engine, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(ai_engine) as session:
        for ticket_id in ("ticket-old", "ticket-new"):
            session.add(Ticket(
                id=ticket_id,
                title=ticket_id,
                description="Synthetic ticket description",
                category=constants.Category.DOCUMENTATION,
                tags=constants.serialize_tags([]),
                department_id=None,
                assigned_agent_id=None,
                creator_user_id="admin-1",
                status=constants.Status.OPEN,
                priority=constants.Priority.NORMAL,
                updated_at=now,
                created_at=now,
                due_at=None,
                deleted_at=None,
            ))
        session.commit()

    monkeypatch.setattr(analysis_results, "consume_analysis_creation_allowance", lambda _: None)
    monkeypatch.setattr(
        jobs_service,
        "enqueue_analysis_result_job",
        lambda result_id: SimpleNamespace(id=f"job-{result_id}"),
    )
    ai_settings.update_settings(
        AISettingsUpdate(
            provider="openrouter",
            model="openai/gpt-oss-20b",
            expected_version=1,
        ),
        requester(),
    )
    old_result = analysis_results.request_analysis("ticket-old", requester())
    ai_settings.update_settings(
        AISettingsUpdate(
            provider="fake",
            model="deterministic-fake-v1",
            expected_version=2,
        ),
        requester(),
    )
    new_result = analysis_results.request_analysis("ticket-new", requester())

    assert (old_result.provider, old_result.model) == ("openrouter", "openai/gpt-oss-20b")
    assert (new_result.provider, new_result.model) == ("fake", "deterministic-fake-v1")
    assert operations.get_analysis_result(old_result.id).provider == "openrouter"


def test_worker_factory_uses_durable_provider_not_legacy_process_setting(monkeypatch):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "openrouter")

    analyzer = build_analyzer(
        provider="fake",
        model="deterministic-fake-v1",
        prompt_version="ticket_summary_v1",
    )

    assert analyzer.analyze(ai_settings._synthetic_snapshot()).summary.startswith("Synthetic")


@pytest.mark.parametrize("role", [constants.Role.MANAGER, constants.Role.AGENT])
def test_non_admin_cannot_manage_ai_settings(ai_engine, role):
    with pytest.raises(AuthorizationError):
        ai_settings.get_settings(requester(role))
