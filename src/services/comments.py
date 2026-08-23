from datetime import datetime, timezone
from .permissions import check_for_access
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
    if check_for_access(requester.role, constants.Role.AGENT):
        if comment.visibility == constants.Visibility.PRIVATE_TO_MANAGER:
            raise AuthorizationError()
        return
    if requester.role != constants.Role.USER:
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

    comments = operations.get_comments(ticket_id, limit, offset, sort_by, sort_order)

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            raise AuthorizationError()
        comments = [
            comment for comment in comments
            if comment.deleted_at is None and comment.visibility == constants.Visibility.PUBLIC
        ]
    elif check_for_access(requester.role, constants.Role.MANAGER):
        comments = [comment for comment in comments if comment.deleted_at is None]
    elif check_for_access(requester.role, constants.Role.AGENT_READONLY):
        comments = [
            comment for comment in comments
            if comment.deleted_at is None and comment.visibility != constants.Visibility.PRIVATE_TO_MANAGER
        ]
    else:
        raise AuthorizationError()

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
        if ticket.creator_user_id != requester.id: raise AuthorizationError()
    return _to_api_comment(comment)

def create_ticket_comment(ticket_id: str, comment_create:api_models.CommentCreate, requester: api_models.User) -> api_models.Comment:
    
    ticket = operations.get_ticket(ticket_id)
    if ticket == None or ticket.deleted_at is not None: raise TicketNotFoundError()

    if check_for_access(requester.role, constants.Role.AGENT) is False and requester.id != ticket.creator_user_id:
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

    if ticket.assigned_agent_id and ticket.assigned_agent_id != requester.id:
        s_notifications.emit(
            ticket.assigned_agent_id,
            "comment_added",
            f"A new visible comment was added to ticket #{ticket_id[:8]}.",
            ticket_id=ticket_id,
            idempotency_key=f"comment-added:{comment.id}:{ticket.assigned_agent_id}",
        )

    return _to_api_comment(res)



def update_comment(ticket_id: str, comment_id: str, new_info: api_models.CommentUpdate, requester: api_models.User) -> api_models.Comment:
    
    comment = operations.get_comment(comment_id)
    if comment is None: raise CommentNotFoundError()
    _check_comment_belongs_to_ticket(comment, ticket_id)

    ticket = operations.get_ticket(comment.ticket_id)
    if ticket is None: raise TicketNotFoundError()

    if comment.deleted_at is not None or ticket.deleted_at is not None: 
        raise CommentNotFoundError()
    if requester.role == constants.Role.USER and comment.author_user_id != requester.id:
        raise AuthorizationError()
    elif requester.role == constants.Role.AGENT and ticket.assigned_agent_id != requester.id: 
        raise AuthorizationError()
    elif check_for_access(requester.role, constants.Role.MANAGER):
        pass
    elif requester.role not in [constants.Role.USER, constants.Role.AGENT]:
        raise AuthorizationError()
    
    
    audit_new_info = new_info.model_dump(exclude_unset=True, mode="json")
    updated_info = new_info.model_dump(exclude_unset=True)

    if not updated_info:
        raise EmptyUpdateError()
    if "body" in updated_info and updated_info["body"] is not None:
        updated_info["body"] = constants.validate_required_text(updated_info["body"], "comment_body", constants.COMMENT_BODY_MAX_LENGTH)
        audit_new_info["body"] = updated_info["body"]
    if requester.role == constants.Role.USER and "visibility" in updated_info and updated_info["visibility"] != constants.Visibility.PUBLIC:
        raise AuthorizationError()
    if updated_info.get("visibility") == constants.Visibility.PRIVATE_TO_MANAGER:
        if check_for_access(requester.role, constants.Role.MANAGER) is False:
            raise AuthorizationError()

    old_info = {}
    for field in updated_info:
        old_value = getattr(comment, field)
        old_info[field] = constants._audit_value(old_value)


    event = api_models.Event(
        id=constants.generate_id(),
        entity_type=constants.EntityType.COMMENT,
        entity_id=comment_id,
        actor_user_id=requester.id,
        event_type=constants.EventType.COMMENT_UPDATED,
        old_value=json.dumps(old_info),
        new_value=json.dumps(audit_new_info), #?
        metadata=None,
        created_at=datetime.now(timezone.utc)
    )

    updated_comment = operations.update_comment_with_event(comment_id, updated_info, event)
    if updated_comment is None:
        raise AuditLogError("Comment could not be updated", code="comment_update_failed")

    return _to_api_comment(updated_comment)

# delete 
def delete_comment(ticket_id: str, comment_id: str, requester: api_models.User) -> bool:
    
    comment = operations.get_comment(comment_id)
    if comment is None:
        raise CommentNotFoundError()
    _check_comment_belongs_to_ticket(comment, ticket_id)
    if comment.deleted_at is not None:
        raise AlreadyDeletedError()

    if comment.author_user_id != requester.id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
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
