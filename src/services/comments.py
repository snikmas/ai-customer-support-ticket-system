"""Comment authorization.

Action matrix for a comment on a ticket the requester may currently access.
"own" means the requester authored the comment. A dash means denied.

| Action            | customer            | assigned agent        | other agent | read-only | manager+ |
|-------------------|---------------------|-----------------------|-------------|-----------|----------|
| list / detail     | own ticket, public  | assigned/NEW, +internal | NEW, +internal | public+internal | all |
| attachment list   | own ticket, public  | assigned/NEW, +internal | NEW, +internal | public+internal | all |
| attachment download| own ticket, public | assigned/NEW, +internal | NEW, +internal | public+internal | all |
| edit body         | own & public only   | own, not manager-private | -         | -         | -        |
| change visibility | own public -> public | own, public/internal | -           | -         | any      |
| delete            | own                 | own                   | -           | -         | any      |
| upload file       | own comment only    | own comment only      | -           | -         | own comment only |
| create comment    | own ticket, public  | assigned/NEW          | NEW         | -         | any      |

Body editing and file upload are author-only for every role: managers/admins
may change visibility or soft-delete, but never replace another author's body.
Read-only users may never create, update, or delete content.
"""

from datetime import datetime, timezone
from .permissions import can_write_ticket_content, check_for_access
from src import constants

from src import models as api_models
from src.db import models as db_models
from src.db import operations
from src.exceptions.domain import AlreadyDeletedError, AuditLogError, AuthorizationError, CommentNotFoundError, EmptyUpdateError, TicketNotFoundError
from src.services import notifications as s_notifications
import json


def _to_api_comment(comment: db_models.Comment) -> api_models.Comment:
    return api_models.Comment.model_validate(comment, from_attributes=True)


def _check_comment_belongs_to_ticket(comment: db_models.Comment, ticket_id: str) -> None:
    if comment.ticket_id != ticket_id:
        raise CommentNotFoundError()


def _check_comment_is_visible(comment: db_models.Comment, requester: api_models.User) -> None:
    if comment.deleted_at is not None:
        raise CommentNotFoundError()
    if requester.role == constants.Role.USER and comment.visibility != constants.Visibility.PUBLIC:
        raise AuthorizationError()
    if check_for_access(requester.role, constants.Role.MANAGER):
        return
    # Read-only staff share the agent visibility subset (public + internal) so
    # the list and direct-detail endpoints agree. Manager-private stays denied.
    if check_for_access(requester.role, constants.Role.AGENT_READONLY):
        if comment.visibility == constants.Visibility.PRIVATE_TO_MANAGER:
            raise AuthorizationError()
        return
    if requester.role != constants.Role.USER:
        raise AuthorizationError()
        
        
def _check_agent_can_access_ticket(ticket: db_models.Ticket, requester: api_models.User) -> None:
    """Mirror the ticket read rule for agents: assigned work or the NEW queue."""
    if (
        ticket.assigned_agent_id != requester.id
        and not (
            ticket.assigned_agent_id is None
            and ticket.status == constants.Status.NEW
        )
    ):
        raise AuthorizationError()


def get_all_comments(
                    ticket_id: str,
                    requester: api_models.User,
                    limit: int,
                    offset: int,
                    sort_by: str,
                    sort_order: str) -> list[api_models.Comment]:
    ticket = operations.get_ticket(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise TicketNotFoundError()

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
        visibilities = (constants.Visibility.PUBLIC,)
    elif check_for_access(requester.role, constants.Role.MANAGER):
        visibilities = None
    elif check_for_access(requester.role, constants.Role.AGENT_READONLY):
        if requester.role == constants.Role.AGENT:
            _check_agent_can_access_ticket(ticket, requester)
        visibilities = (constants.Visibility.PUBLIC, constants.Visibility.INTERNAL)
    else:
        raise AuthorizationError()

    # Visibility filtering happens in SQL so pages are not shortened by rows
    # the requester cannot see.
    comments = operations.get_comments(
        ticket_id,
        limit,
        offset,
        sort_by,
        sort_order,
        visibilities=visibilities,
    )

    return [_to_api_comment(comment) for comment in comments]

def get_comment(ticket_id: str, comment_id: str, requester: api_models.User) -> api_models.Comment:

    comment = operations.get_comment(comment_id)
    if comment is None:
        raise CommentNotFoundError()
    _check_comment_belongs_to_ticket(comment, ticket_id)
    if comment.deleted_at is not None:
        raise CommentNotFoundError()
    
    ticket = operations.get_ticket(comment.ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise TicketNotFoundError()

    _check_comment_is_visible(comment, requester)

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
    elif requester.role == constants.Role.AGENT:
        _check_agent_can_access_ticket(ticket, requester)
    return _to_api_comment(comment)

def create_ticket_comment(ticket_id: str, comment_create:api_models.CommentCreate, requester: api_models.User) -> api_models.Comment:
    
    ticket = operations.get_ticket(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise TicketNotFoundError()

    if not can_write_ticket_content(requester.role):
        raise AuthorizationError()

    # Commenting follows ticket read access: managers anywhere, agents only on
    # their assigned work or the unassigned NEW queue, customers only their own.
    if check_for_access(requester.role, constants.Role.MANAGER):
        pass
    elif requester.role == constants.Role.AGENT:
        _check_agent_can_access_ticket(ticket, requester)
    elif requester.id != ticket.creator_user_id:
        raise AuthorizationError()
    if requester.role == constants.Role.USER and comment_create.visibility != constants.Visibility.PUBLIC:
        raise AuthorizationError()
    if comment_create.visibility == constants.Visibility.PRIVATE_TO_MANAGER and check_for_access(requester.role, constants.Role.MANAGER) is False:
        raise AuthorizationError()

    if comment_create.parent_comment_id is not None:
        parent = operations.get_comment(comment_create.parent_comment_id)
        if parent is None:
            raise CommentNotFoundError()
        _check_comment_belongs_to_ticket(parent, ticket_id)
        _check_comment_is_visible(parent, requester)

    now = datetime.now(timezone.utc)
    body = constants.validate_required_text(comment_create.body, "comment_body", constants.COMMENT_BODY_MAX_LENGTH)
    comment = db_models.Comment(
        id=constants.generate_id(),
        ticket_id=ticket_id,
        author_user_id=requester.id,
        body=body,
        visibility=comment_create.visibility,
        edited_at=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by_user_id=None,
        parent_comment_id=comment_create.parent_comment_id,
        attachments_count=0,
        source=constants.Source.API
    )

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.COMMENT,
        entity_id=comment.id,
        actor_user_id=requester.id,
        event_type=constants.EventType.COMMENT_CREATED,
        old_value=None,
        new_value=json.dumps(_to_api_comment(comment).model_dump(mode="json")),
        metadata=None,
        created_at=now
    )
    res = operations.create_comment_with_event(comment, event)
    if res is None:
        raise AuditLogError("Comment could not be created", code="comment_create_failed")

    if (
        ticket.assigned_agent_id
        and ticket.assigned_agent_id != requester.id
        and comment.visibility != constants.Visibility.PRIVATE_TO_MANAGER
    ):
        s_notifications.emit(
            ticket.assigned_agent_id,
            "comment_added",
            f"A new visible comment was added to ticket #{ticket_id[:8]}.",
            ticket_id=ticket_id,
            idempotency_key=f"comment-added:{comment.id}:{ticket.assigned_agent_id}",
        )

    return _to_api_comment(res)



def _authorize_comment_update(
    ticket_id: str,
    comment: db_models.Comment | None,
    ticket: db_models.Ticket | None,
    updated_info: dict,
    requester: api_models.User,
    actor: db_models.User | None,
) -> None:
    """Re-check the update policy against the currently locked rows.

    Runs authoritatively inside the write transaction. Any condition that could
    have changed since the request's first read (visibility, deletion,
    authorship, ticket access, and the actor's role/account state) is
    re-evaluated here so a stale request cannot undo a newer restriction.

    ``requester`` carries the token identity (its subject is stable), but the
    role and account state come from the freshly locked ``actor`` row, never
    from the role claim captured when the request arrived. If the actor row is
    missing, banned, or soft-deleted the write is denied.
    """
    if comment is None:
        raise CommentNotFoundError()
    _check_comment_belongs_to_ticket(comment, ticket_id)
    if ticket is None:
        raise TicketNotFoundError()
    if comment.deleted_at is not None or ticket.deleted_at is not None:
        raise CommentNotFoundError()

    if (
        actor is None
        or actor.deleted_at is not None
        or actor.user_status != constants.UserStatus.ACTIVE
    ):
        raise AuthorizationError()

    current_role = actor.role
    if not can_write_ticket_content(current_role):
        raise AuthorizationError()

    is_author = comment.author_user_id == requester.id
    has_manager_rights = check_for_access(current_role, constants.Role.MANAGER)

    if current_role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
        if comment.visibility != constants.Visibility.PUBLIC:
            raise AuthorizationError()
    elif current_role == constants.Role.AGENT:
        if ticket.assigned_agent_id != requester.id:
            raise AuthorizationError()
        if comment.visibility == constants.Visibility.PRIVATE_TO_MANAGER:
            raise AuthorizationError()
    elif has_manager_rights:
        pass
    else:
        raise AuthorizationError()

    if "body" in updated_info and not is_author:
        raise AuthorizationError()

    if "visibility" in updated_info:
        requested_visibility = updated_info["visibility"]
        if not is_author and not has_manager_rights:
            raise AuthorizationError()
        if (
            requested_visibility == constants.Visibility.PRIVATE_TO_MANAGER
            and not has_manager_rights
        ):
            raise AuthorizationError()
        if (
            current_role == constants.Role.USER
            and requested_visibility != constants.Visibility.PUBLIC
        ):
            raise AuthorizationError()


def update_comment(ticket_id: str, comment_id: str, new_info: api_models.CommentUpdate, requester: api_models.User) -> api_models.Comment:

    updated_info = new_info.model_dump(exclude_unset=True)
    audit_new_info = new_info.model_dump(exclude_unset=True, mode="json")
    if not updated_info:
        raise EmptyUpdateError()

    if "body" in updated_info and updated_info["body"] is not None:
        updated_info["body"] = constants.validate_required_text(
            updated_info["body"], "comment_body", constants.COMMENT_BODY_MAX_LENGTH
        )
        audit_new_info["body"] = updated_info["body"]

    def mutate(comment, ticket, actor):
        # Authoritative re-check against the locked rows and the actor's current
        # persisted state, then build the audit event from the state actually
        # modified in this transaction.
        _authorize_comment_update(
            ticket_id, comment, ticket, updated_info, requester, actor
        )

        old_info = {}
        for field in updated_info:
            old_info[field] = constants._audit_value(getattr(comment, field))
        # History needs the visibility at the time of each body snapshot.
        old_info["visibility"] = constants._audit_value(comment.visibility)
        audit_new_info["visibility"] = constants._audit_value(
            updated_info.get("visibility", comment.visibility)
        )

        event = api_models.Event(
            id=constants.generate_id(),
            entity_type=constants.EntityType.COMMENT,
            entity_id=comment_id,
            actor_user_id=requester.id,
            event_type=constants.EventType.COMMENT_UPDATED,
            old_value=json.dumps(old_info),
            new_value=json.dumps(audit_new_info),
            metadata=None,
            created_at=datetime.now(timezone.utc),
        )
        return updated_info, event

    updated_comment = operations.update_comment_with_event(
        comment_id, mutate, actor_user_id=requester.id
    )
    if updated_comment is None:
        raise CommentNotFoundError()

    return _to_api_comment(updated_comment)
# delete 
def delete_comment(ticket_id: str, comment_id: str, requester: api_models.User) -> bool:
    
    comment = operations.get_comment(comment_id)
    if comment is None:
        raise CommentNotFoundError()
    _check_comment_belongs_to_ticket(comment, ticket_id)
    if comment.deleted_at is not None:
        raise AlreadyDeletedError()

    if not can_write_ticket_content(requester.role):
        raise AuthorizationError()

    if comment.author_user_id != requester.id:
        if check_for_access(requester.role, constants.Role.MANAGER) is False:
            raise AuthorizationError()
        
    now = datetime.now(timezone.utc)
    delete_info = {
        "deleted_at": now,
        "updated_at": now,
        "deleted_by_user_id": requester.id
    }
    

    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.COMMENT,
        entity_id=comment_id,
        actor_user_id=requester.id,
        event_type=constants.EventType.COMMENT_DELETED,
        old_value=constants._audit_json({"deleted_at": comment.deleted_at, "updated_at": comment.updated_at}),
        new_value=constants._audit_json(delete_info),
        metadata=None,
        created_at=now
    )

    if operations.delete_comment_with_event(comment_id, delete_info, event) is False:
        raise AuditLogError("Comment could not be deleted", code="comment_delete_failed")

    return True
