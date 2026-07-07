from datetime import datetime, timezone
from .permissions import check_for_access
from src import constants

from src import models as api_models
from src.db import models as db_models
from src.db import operations
import json


def _to_api_comment(comment: db_models.Comment) -> api_models.Comment:
    return api_models.Comment.model_validate(comment, from_attributes=True)


def get_all_comments(ticket_id: str, requester: api_models.User) -> list[api_models.Comment] | None:
    ticket = operations.get_ticket(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        return None

    comments = operations.get_comments(ticket_id)

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id:
            return None
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
        return None

    return [_to_api_comment(comment) for comment in comments]

def get_comment(comment_id: str, requester: api_models.User) -> api_models.Comment | None:

    comment = operations.get_comment(comment_id)
    if comment is None:
        return None
    
    ticket = operations.get_ticket(comment.ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        return None

    if requester.role == constants.Role.USER:
        if ticket.creator_user_id != requester.id: return None
        if comment.deleted_at is not None: return None
        if comment.visibility != constants.Visibility.PUBLIC: return None
    elif check_for_access(requester.role, constants.Role.AGENT):
        if comment.deleted_at is not None: return None
        if comment.visibility == constants.Visibility.PRIVATE_TO_MANAGER: return None
    elif check_for_access(requester.role, constants.Role.MANAGER): 
        pass
    else: 
        return None
    return _to_api_comment(comment)

def create_ticket_comment(ticket_id: str, comment_create:api_models.CommentCreate, requester: api_models.User) -> api_models.Comment | None:
    
    ticket = operations.get_ticket(ticket_id)
    if ticket == None or ticket.deleted_at is not None: return None

    if check_for_access(requester.role, constants.Role.AGENT) is False and requester.id != ticket.creator_user_id:
        return None
    if requester.role == constants.Role.USER and comment_create.visibility != constants.Visibility.PUBLIC:
        return None
    if comment_create.visibility == constants.Visibility.PRIVATE_TO_MANAGER and check_for_access(requester.role, constants.Role.MANAGER) is False:
        return None

    now = datetime.now(timezone.utc)
    comment = db_models.Comment(
        id=constants.generate_id(),
        ticket_id=ticket_id,
        author_user_id=requester.id,
        body=comment_create.body,
        visibility=comment_create.visibility,
        edited_at=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by_user_id=None,
        parent_comment_id=comment_create.parent_comment_id,
        attachments_count=comment_create.attachments_count or 0,
        source=comment_create.source
    )

    res = operations.create_comment(comment)
    if res is None:
        return None

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
    event_res = operations.create_event(event)
    if event_res is False: return None

    return _to_api_comment(res)



def update_comment(comment_id: str, new_info: api_models.CommentUpdate, requester: api_models.User) -> api_models.Comment | None:
    
    comment = operations.get_comment(comment_id)
    if comment is None: return None

    ticket = operations.get_ticket(comment.ticket_id) #comment.ticked id couldn't be none cuz its non-none value
    if ticket is None: return None

    if comment.deleted_at is not None or ticket.deleted_at is not None: 
        return None # but in bot sure with amdint/agents? can they?
    if requester.role == constants.Role.USER and comment.author_user_id != requester.id:
        return None
    elif requester.role == constants.Role.AGENT and ticket.assigned_agent_id != requester.id: 
        return None
    elif check_for_access(requester.role, constants.Role.MANAGER):
        pass
    elif requester.role not in [constants.Role.USER, constants.Role.AGENT]:
        return None
    
    
    audit_new_info = new_info.model_dump(exclude_unset=True, mode="json")
    updated_info = new_info.model_dump(exclude_unset=True)

    if not updated_info:
        raise ValueError('empty_update')
    if requester.role == constants.Role.USER and "visibility" in updated_info and updated_info["visibility"] != constants.Visibility.PUBLIC:
        return None
    if updated_info.get("visibility") == constants.Visibility.PRIVATE_TO_MANAGER:
        if check_for_access(requester.role, constants.Role.MANAGER) is False:
            return None

    requested_fields = updated_info.keys()
    old_info = {}
    #later can create a helper fuctino with it
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

    updated_comment = operations.update_comment(comment_id, updated_info)
    if updated_comment is None:
        raise ValueError("Some error during updating, the operation canceled")
        
    event_res = operations.create_event(event)
    if event_res is False: return None
    return _to_api_comment(updated_comment)

# delete 
def delete_comment(comment_id: str, requester: api_models.User) -> bool:
    
    comment = operations.get_comment(comment_id)
    if comment is None:
        raise ValueError('ticket_not_found')

    if comment.author_user_id != requester.id:
        if check_for_access(requester.role, constants.Role.ADMIN) is False:
            raise PermissionError
        
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

    if operations.delete_comment(comment_id, delete_info) is False:
        raise ValueError("Some error during deleting, the operation cancelled")
        
    event_res = operations.create_event(event)
    if event_res is False:
        return None
    return True
