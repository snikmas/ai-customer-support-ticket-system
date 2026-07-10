# functions that the worker runs
import requests
from . import get_ticket_analysis_queue
from rq import Queue

def analyze_ticket(ticket_id: str) -> str: # returns job_id
    # @ worker tasK: recieve ticket_id -> load ticket later -> fake/small analysis first -> later save result to db
    queue = get_ticket_analysis_queue()
    job = queue.get(ticket_id)