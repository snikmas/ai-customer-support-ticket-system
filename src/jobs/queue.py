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

# Highest priority first. A shared RQ worker drains queues in this order, so
# listing analysis first means a routing backlog can never delay user-facing
# analysis work. Routing jobs stay short and the reconciler is capped, so the
# reverse risk (a sustained analysis backlog delaying routing) is bounded by
# the analysis rate limit and job timeout. Larger deployments instead run one
# dedicated worker per queue; this tuple is the shipped local default.
WORKER_QUEUE_ORDER = (QUEUE_NAME, ROUTING_QUEUE_NAME)

def get_ticket_jobs_queue() -> Queue:
    queue = Queue(QUEUE_NAME, connection=get_redis_client())
    return queue


def get_ticket_routing_queue() -> Queue:
    """Keep short routing jobs separate from slower inspection/LLM work."""
    return Queue(ROUTING_QUEUE_NAME, connection=get_redis_client())
