"""Create a small, synthetic, repeatable dataset for a local demonstration."""

import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src import constants
from src.core import hash_password
from src.core.config import ATTACHMENTS_DIR
from src.db.engine import engine
from src.db.models import AgentProfile, Attachment, Comment, Department, Notification, Skill, Ticket, TicketLink, User
from src.storage import LocalAttachmentStorage


DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "").strip()


def make_user(session: Session, nickname: str, *, first_name: str, last_name: str, phone: str, email: str, role: constants.Role) -> User:
    existing = session.scalar(select(User).where(User.nickname == nickname))
    if existing is not None:
        return existing
    now = constants.utc_now()
    user = User(
        id=constants.generate_id(), nickname=nickname, avatar_url=None,
        first_name=first_name, last_name=last_name, phone=phone, email=email,
        password=hash_password(DEMO_PASSWORD), role=role,
        user_status=constants.UserStatus.ACTIVE, deleted_at=None,
        created_at=now, updated_at=now,
    )
    session.add(user)
    session.flush()
    return user


def main() -> None:
    if not DEMO_PASSWORD:
        raise SystemExit("Set DEMO_PASSWORD for this local-only demo command.")

    with Session(engine) as session, session.begin():
        if session.scalar(select(User).where(User.nickname == "demo-customer")) is not None:
            print("Demo data already exists; nothing changed.")
            return

        now = constants.utc_now()
        department = Department(
            id=constants.generate_id(), name="Demo API Support",
            normalized_name="demo api support",
            description="Synthetic department for the local walkthrough.",
            created_at=now, updated_at=now, deleted_at=None,
        )
        skill = Skill(
            id=constants.generate_id(), name="Demo API", normalized_name="demo api",
            description="Synthetic routing skill.", created_at=now,
            updated_at=now, deleted_at=None,
        )
        session.add_all([department, skill])
        session.flush()

        manager = make_user(session, "demo-manager", first_name="Demo", last_name="Manager", phone="+15550001001", email="demo-manager@example.invalid", role=constants.Role.MANAGER)
        agent = make_user(session, "demo-agent", first_name="Demo", last_name="Agent", phone="+15550001002", email="demo-agent@example.invalid", role=constants.Role.AGENT)
        customer = make_user(session, "demo-customer", first_name="Demo", last_name="Customer", phone="+15550001003", email="demo-customer@example.invalid", role=constants.Role.USER)
        profile = AgentProfile(
            user_id=agent.id, availability_status=constants.AvailabilityStatus.AVAILABLE,
            availability_reason=None, availability_note="Synthetic demo agent",
            unavailable_until=None, max_active_tickets=10, last_assigned_at=None,
            department_id=department.id, created_at=now, updated_at=now,
        )
        profile.skills = [skill]
        session.add(profile)

        first = Ticket(
            id=constants.generate_id(), title="Demo API request returns a timeout",
            description="Synthetic ticket for search, customer info, comments, and routing.",
            category=constants.Category.API_ERROR,
            tags=constants.serialize_tags([constants.Tag.API_KEY, constants.Tag.TIMEOUT]),
            department_id=department.id, assigned_agent_id=agent.id,
            creator_user_id=customer.id, status=constants.Status.OPEN,
            priority=constants.Priority.HIGH, due_at=now + timedelta(hours=4),
            created_at=now, updated_at=now, deleted_at=None,
        )
        second = Ticket(
            id=constants.generate_id(), title="Demo related documentation question",
            description="A second synthetic issue linked to the first one.",
            category=constants.Category.DOCUMENTATION,
            tags=constants.serialize_tags([constants.Tag.PYTHON]),
            department_id=department.id, assigned_agent_id=None,
            creator_user_id=customer.id, status=constants.Status.NEW,
            priority=constants.Priority.NORMAL, due_at=now + timedelta(hours=8),
            created_at=now, updated_at=now, deleted_at=None,
        )
        first.requested_skills = [skill]
        second.requested_skills = [skill]
        session.add_all([first, second])
        session.flush()

        comment = Comment(
            id=constants.generate_id(), ticket_id=first.id, author_user_id=customer.id,
            body="I attached the request sample and the observed timeout details.",
            visibility=constants.Visibility.PUBLIC, edited_at=None, created_at=now,
            updated_at=now, deleted_at=None, deleted_by_user_id=None,
            parent_comment_id=None, attachments_count=1, source=constants.Source.WEB,
        )
        session.add(comment)
        session.flush()
        session.add(TicketLink(
            id=constants.generate_id(), ticket_id=min(first.id, second.id),
            related_ticket_id=max(first.id, second.id), created_by_user_id=manager.id,
            created_at=now,
        ))
        session.add(Notification(
            id=constants.generate_id(), recipient_user_id=agent.id,
            notification_type="demo_assignment", ticket_id=first.id,
            message="A synthetic demo ticket is assigned to you.", created_at=now,
            read_at=None, idempotency_key="demo-assignment",
        ))
        storage_key = f"{uuid4().hex}.txt"
        content = b"synthetic demo attachment\n"
        session.add(Attachment(
            id=constants.generate_id(), comment_id=comment.id, storage_key=storage_key,
            original_filename="request-sample.txt", content_type="text/plain",
            size_bytes=len(content), created_by_user_id=customer.id, created_at=now,
            deleted_at=None,
        ))

    LocalAttachmentStorage(ATTACHMENTS_DIR).save(storage_key, content)
    print("Synthetic demo data created.")


if __name__ == "__main__":
    main()
