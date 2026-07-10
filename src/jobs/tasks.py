# functions that the worker runs
# shouldn't touch the queue

def analyze_ticket(ticket_id: str) -> dict: # returns job_id
    # LOAD A TICKET from db
    # run llm analysis
    # save result to db
    return {
        "ticket_id": ticket_id,
        "analysis": "analysis result"
    }