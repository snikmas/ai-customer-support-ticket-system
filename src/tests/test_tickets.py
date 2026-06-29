from src import db
from fastapi.testclient import TestClient
from main import app
from src import constants
from .fixtures import setup_db

client = TestClient(app)

# =========================================================================
# ===================== END POINTS ========================================
def test_is_endpoint_gets_all_tickets():
    response = client.get("/tickets")
    assert response.status_code == 200, response.text()
    assert "res" in response.json()

def test_is_endpoint_creates_ticket():
    ticket_id = None
    try:
        response = client.post("/tickets", json = {
            "title": "test_ticket1",
            "description": "test_description",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "tags": []
        })
        assert response.status_code == 201, response.text()

        data = response.json()
        ticket_id = data['res']['id']

        saved_ticket = db.get_ticket(ticket_id)
        assert saved_ticket is not None
    finally:
        if ticket_id is not None:
            db.delete_ticket(ticket_id)
# do i need it?
def test_is_endpoint_works_get_ticket():
    ticket_id = None
    try:
        response = client.post("/tickets", json = {
            "title": "test_ticket1",
            "description": "test_description",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "tags": []
        })
        assert response.status_code == 201, response.text()

        data = response.json()
        ticket_id = data['res']['id']

        response = client.get(f"/tickets/{ticket_id}")
        if response:
            data = response.json()
            new_ticket_id = data['res']['id']
            assert new_ticket_id == ticket_id
    finally:
        db.delete_ticket(ticket_id)
        db.delete_user(new_ticket_id)

def test_is_endpoint_works_update_tickets():
    ticket_id = None
    try:
        response = client.post("/tickets", json = {
            "title": "test_ticket1",
            "description": "test_description",
            "category": constants.Category.ACCOUNT_ACCESS.value,
            "tags": []
        })
        assert response.status_code == 201, response.text

        data = response.json()
        ticket_id = data["res"]["id"]

        saved_ticket = db.get_ticket(ticket_id)
        assert saved_ticket is not None

        #update
        response = client.patch(f"/tickets/{ticket_id}", json = {
            "tags": [constants.Tag.API_KEY.value]
        })

        assert response.status_code == 201, response.text

        saved_ticket = db.get_ticket(ticket_id)
        assert "api-key" in saved_ticket["tags"]
    finally:
        if ticket_id is not None:
            db.delete_ticket(ticket_id)

# ==================================================================================
# ===================== TEST PATCH ENDPOINT ========================================
# here should be a helper 
def test_user_changes_ticket_should_raise_exception(setup_db):
    pass
def test_no_updated_info_should_raise_exception(setup_db):
    pass
def test_ticket_doesnt_exist(setup_db):
    pass
def test_user_doesnt_exist(setup_db):
    pass
def test_user_tries_change_ticket_should_raise_exception(setup_db):
    pass
def test_only_assigned_agent_manager_admins_should_be_able_update(setup_db):
    pass
def test_invalid_status_transition(setup_db):
    pass