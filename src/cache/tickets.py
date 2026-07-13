# TICKET CACHE LOGIC ONLY
from . import get_redis_client
from src.constants import logger
from src.exceptions import CacheUnavailableError
from redis import RedisError
from src.models import Ticket
import json
from . import build_ticket_key


def check_ticket(ticket_id: str) -> Ticket | None:
#   Redis gives bytes
#       ↓ .decode("utf-8")
#   JSON text (str)
#       ↓ json.loads(...)
#   normal Python dictionary
#       ↓ Ticket.model_validate(...)
#   Pydantic Ticket object
    try:
        client = get_redis_client()
        if client is None:
            return None
        
        ticket_key = build_ticket_key(ticket_id)

        raw_ticket = client.get(ticket_key) 
        if raw_ticket is None:
            return None
        

        json_text = raw_ticket.decode('utf-8')
        data = json.loads(json_text)
        return Ticket.model_validate(data)

    except RedisError as exc:
        logger.exception("Redis unavailable while cheking the ticket")
        raise CacheUnavailableError() from exc
    
def delete_ticket(ticket_id: str) -> bool:
    try:
        client = get_redis_client()
        if client is None: return False

        ticket_key = build_ticket_key(ticket_id)
        #do i have to check if ticket key is none?
        return client.delete(ticket_key)

    except RedisError as exc:
        raise CacheUnavailableError from exc

def cache_ticket(ticket: Ticket) -> bool:
#   When saving a ticket:

#   Pydantic Ticket object
#       ↓ model_dump(mode="json")
#   normal Python dictionary
#       ↓ json.dumps(...)
#   JSON text (str)
#       ↓ client.set(...)
#   Redis stores bytes
    try:
        client = get_redis_client()
        if client is None:
            raise CacheUnavailableError

        ticket_dict = ticket.model_dump(mode='json')
        ticket_json = json.dumps(ticket_dict)

        ticket_key = build_ticket_key(ticket.id)
        return client.set(ticket_key, ticket_json, ex=300) #from pydantic -> json -> bytes?
    except RedisError as exc:
        raise CacheUnavailableError() from exc