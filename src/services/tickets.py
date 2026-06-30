from datetime import datetime

from src import constants
from src.models import models as api_models
from src.db import models as db_models
from src.db import operations

def create_ticket(ticket_data: api_models.TicketCreate) -> db_models.Ticket:
    now = datetime.now()

    ticket = db_models.Ticket(
        id=constants.generate_id(),
        title=ticket_data.title,
        description=ticket_data.description,
        category=ticket_data.category,
        tags=ticket_data.tags,
        assigned_agent_id=None,
        creator_user_id=None,
        # status=ticket_data.,
        priority=ticket_data.p,
        updated_at=now,
        created_at=now
    )
    operations.create_ticket(ticket)
    return ticket