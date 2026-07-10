# only queue infrastructure
# create redis connesion
# create queue
# return queue object
# no ticket logic/fastapi here
# own rq queue configuration
from rq import Queue
from src.cache import get_redis_client


QUEUE_NAME = 'ticket_analysis'

def get_ticket_analysis_queue() -> Queue:
    queue = Queue(QUEUE_NAME, connection=get_redis_client())
    return queue

# queue = Queue(connection=Redis)
# job = queue.enqueue(func, 'link')