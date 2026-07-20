# only queue infrastructure
# create redis connesion
# create queue
# return queue object
# no ticket logic/fastapi here
# own rq queue configuration
from rq import Queue
from src.cache import get_redis_client

QUEUE_NAME = 'ticket_jobs'
ROUTING_QUEUE_NAME = "ticket_routing"

def get_ticket_jobs_queue() -> Queue:
    queue = Queue(QUEUE_NAME, connection=get_redis_client())
    return queue


def get_ticket_routing_queue() -> Queue:
    """Keep short routing jobs separate from slower inspection/LLM work."""
    return Queue(ROUTING_QUEUE_NAME, connection=get_redis_client())
