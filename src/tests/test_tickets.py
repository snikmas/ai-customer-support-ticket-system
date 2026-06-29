from src import db
from fastapi.testclient import TestClient
from fastapi import HTTPException
from main import app
import src.models as models
from src import constants 
from fixtures import setup_db
import pytest

client = TestClient(app)

# =========================================================================
# ===================== END POINTS ========================================
def test_is_endpoint_gets_all_tickets(setup_db):
    response = client.get("/tickets")
    assert response.status_code == 200, response.text()
    assert "res" in response.json()

def test_is_endpoint_creates_ticket(setup_db):
    ticket_id = None
    response = client.post("/tickets", json = {
        "title": "test_ticket1",
        "description": "test_description",
        "category": constants.Category.ACCOUNT_ACCESS.value,
        "tags": []},
        params={
            "user_id": '666'
        }
        )
    assert response.status_code == 201, response.text()

    data = response.json()
    ticket_id = data['res']['id']

    saved_ticket = db.get_ticket(ticket_id)
    assert saved_ticket is not None

def test_is_endpoint_works_get_ticket(setup_db):
    ticket_id = None

    user_id = '666'
    ticket_id = '123'

    response = client.get(f"/tickets/{ticket_id}")
    if response:
        data = response.json()
        new_ticket_id = data['res']['id']
        assert new_ticket_id == ticket_id
    

def test_is_endpoint_works_update_tickets(setup_db):
    admin = setup_db['admin']
    ticket_id = None
    try:
        response = client.post("/tickets", json = {
            "title": "test_ticket1",
            "description": "test_description",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "tags": []
        },
        params={
            'user_id': admin.id
        }
        )
        assert response.status_code == 201, response.text

        data = response.json()
        ticket_id = data["res"]["id"]

        saved_ticket = db.get_ticket(ticket_id)
        assert saved_ticket is not None

        #update
        response = client.patch(
            f"/tickets/{ticket_id}",
            params={"requester_id": admin.id},
            json={"tags": [constants.Tag.API_KEY.value]},
        )

        assert response.status_code == 201, response.text

        saved_ticket = db.get_ticket(ticket_id)
        assert "api-key" in saved_ticket["tags"]
    finally:
        if ticket_id is not None:
            db.delete_ticket(ticket_id)

# ==================================================================================
# ===================== TEST PATCH ENDPOINT ========================================
def test_no_updated_info_should_raise_exception(setup_db):
    user = setup_db['ordinary_user']
    ticket = setup_db['new_ticket']
    
    response = client.patch(f"/tickets/{ticket.id}", json={ #json or data?
        'new_info': None,
        'ticket_id': ticket.id,
        'requester_id': user.id
    })

    assert response.status_code == 422
    
def test_ticket_doesnt_exist(setup_db):
    user = setup_db['ordinary_user']
    ticket = setup_db['new_ticket']
    
    response = client.patch(f"/tickets/{ticket.id}", json={ #json or data?
        'new_info': None,
        'ticket_id': '000000000000000',
        'requester_id': user.id
    })

    assert response.status_code == 422
    

def test_user_doesnt_exist(setup_db):
    ticket = setup_db['new_ticket']
    
    response = client.patch(f"/tickets/{ticket.id}", json={ #json or data?
        'new_info': None,
        'ticket_id': ticket.id,
        'requester_id': '24343'
    }) 
    assert response.status_code == 422


def test_only_assigned_agent_manager_admins_should_be_able_update(setup_db):
    user = setup_db['ordinary_user']
    ticket = setup_db['new_ticket']
    admin = setup_db['admin']

    response = client.patch(f"/tickets/{ticket.id}", 
                params={
                    "requester_id": admin.id
                },
                json={
                    "priority": constants.Priority.HIGH.value
                }
    ) 
    
    
    assert response.status_code == 201, response.text
    
    response = client.patch(
        f"/tickets/{ticket.id}",
        params={"requester_id": user.id},
        json={"priority": constants.Priority.LOW.value},
    )
    assert response.status_code == 403
    
def test_invalid_status_transition(setup_db):
    user = setup_db['ordinary_user']
    ticket = setup_db['new_ticket']
    admin = setup_db['admin']


    response = client.patch(f"/tickets/{ticket.id}", 
        params={
            "requester_id": admin.id
        })
    assert response.status_code == 422, response.text
    
    response = client.patch(f"/tickets/{ticket.id}", 
        params={
            "requester_id": admin.id
            },
        json={"status": constants.Status.CLOSED.value}
    )


    assert response.status_code == 409, response.text
    
    
