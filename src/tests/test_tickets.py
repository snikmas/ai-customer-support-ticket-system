from src import db
from fastapi.testclient import TestClient
from main import app
from src import constants
client = TestClient(app)

# =========================================================================
# ===================== END POINTS ========================================
def test_get_all_tickets():
    response = client.get("/tickets")
    assert response.status_code == 200, response.text()
    assert "res" in response.json()

def test_create_ticket():
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
def test_get_ticket():
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

        response = client.get(f"/tickets/{ticket_id}")
        if response:
            data = response.json()
            new_ticket_id = data['res']['id']
            assert new_ticket_id == ticket_id
    finally:
        db.delete_ticket(ticket_id)

def test_update_tickets():
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