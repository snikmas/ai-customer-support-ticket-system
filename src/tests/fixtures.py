import pytest
import src.models as models
import src.constants as const
from datetime import datetime, timedelta
import src.db as db

@pytest.fixture
def setup_db():
    db.delete_all_tickets()
    db.delete_all_users()

    admin = models.User(
        id='001',
        nickname='Admin',
        avatar_url=None,
        first_name='John',
        last_name='Smith',
        phone='123456789',
        email='admin@mail.ru',
        role=const.Roles.ADMIN,
        updated_at=datetime.now(),
        created_at=datetime.now(),
    )

    assigned_agent = models.User(
        id='521',
        nickname='lovely_ag',
        avatar_url='lovely_pic.png',
        first_name='Oliver',
        last_name='Green',
        phone='1111111111',
        email='dear_mail@gmail.com',
        role=const.Roles.AGENT,
        updated_at=datetime.now(),
        created_at=datetime.now(),
    )

    random_agent = models.User(
        id='666',
        nickname='Singed',
        avatar_url='no_pic.png',
        first_name="James",
        last_name="Brown",
        phone='222222222',
        email='random_main@gmail.ru',
        role=const.Roles.AGENT,
        updated_at=datetime.now(),
        created_at=datetime.now(),
    )

    ordinary_user = models.User(
        id='124354',
        nickname='just_a_user',
        avatar_url=None,
        first_name='Helen',
        last_name="Norris",
        phone='55555',
        email='my_mail@gmail.com',
        role=const.Roles.USER,
        updated_at=datetime.now(),
        created_at=datetime.now(),
    )
    
    new_ticket = models.Ticket(
        id="123",
        title="test_title",
        description="super test desc",
        category=const.Category.API_ERROR,
        tags=[const.Tag.TIMEOUT],
        assigned_agent_id=None,
        creator_user_id='666',
        status=const.Status.NEW,
        priority=const.Priority.NORMAL,
        updated_at=datetime.now(),
        created_at=datetime.now(),
        due_at=datetime.now() + timedelta(hours=2)
    )

    new_ticket.category = str(new_ticket.category.value)
    new_ticket.tags = str(new_ticket.tags)
    new_ticket.status = str(new_ticket.status.value)
    new_ticket.priority = str(new_ticket.priority.value)
    
    assigned_ticket = models.Ticket(
        id="12321",
        title="assigned_ticket_title",
        description="super test desc",
        category=const.Category.AGENT_WORKFLOW,
        tags=[const.Tag.TIMEOUT],
        assigned_agent_id='521',
        creator_user_id='124354',
        status=const.Status.IN_PROGRESS,
        priority=const.Priority.NORMAL,
        updated_at=datetime.now(),
        created_at=datetime.now(),
        due_at=datetime.now() + timedelta(hours=2)
    )

    assigned_ticket.category = str(assigned_ticket.category.value)
    assigned_ticket.tags = str(assigned_ticket.tags)
    assigned_ticket.status = str(assigned_ticket.status.value)
    assigned_ticket.priority = str(assigned_ticket.priority.value)

    db.insert_user(admin.__dict__)
    db.insert_user(ordinary_user.__dict__)
    db.insert_user(random_agent.__dict__)
    db.insert_user(assigned_agent.__dict__)

    db.insert_ticket(new_ticket.__dict__)
    db.insert_ticket(assigned_ticket.__dict__)


    yield {
        'admin': admin,
        'ordinary_user': ordinary_user,
        'random_agent': random_agent,
        'assigned_agent': assigned_agent,

        'new_ticket': new_ticket,
        'assigned_ticket': assigned_ticket
    }
    
    db.delete_all_tickets()
    db.delete_all_users()

