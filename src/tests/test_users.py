from src import db
from fastapi.testclient import TestClient
from main import app
from src import constants
client = TestClient(app)

# =========================================================================
# ===================== END POINTS ========================================
def test_get_all_users():
    response = client.get("/users")
    assert response.status_code == 200, response.text()
    assert "res" in response.json()

def test_create_user():
    user_id = None
    try:
        response = client.post("/users", json = {
            "nickname": "test1",
            "avatar_url": "ash",
            "first_name": "name1",
            "last_name": "name2",
            "phone": "phone1",
            "email": "mail",
        })
        assert response.status_code == 201, response.text

        data = response.json()
        user_id = data['res']['id']

        saved_user = db.get_user(user_id)
        assert saved_user is not None
    finally:
        if user_id is not None:
            db.delete_user(user_id)

def test_get_user():
    user_id = None
    try:
        response = client.post("/users", json = {
            "nickname": "test1",
            "first_name": "name1",
            "last_name": "name2",
            "phone": "phone1",
            "email": "mail",
        })
        assert response.status_code == 201, response.text

        data = response.json()
        user_id = data['res']['id']


        response = client.get(f"/users/{user_id}")
        if response:
            new_user_id = data['res']['id']
            assert new_user_id == user_id
    finally:
        db.delete_user(user_id)

def test_update_users():
    user_id = None
    try:
        response = client.post("/users", json = {
            "nickname": "test1",
            "first_name": "name1",
            "last_name": "name2",
            "phone": "phone1",
            "email": "mail",
        })
        assert response.status_code == 201, response.text

        data = response.json()
        user_id = data["res"]["id"]

        saved_user = db.get_user(user_id)
        assert saved_user is not None

        #update
        response = client.patch(f"/users/{user_id}", json = {
            "nickname": "nameTest"
        })

        saved_user = db.get_user(user_id)
        assert "nameTest" == saved_user["nickname"]
    finally:
        if user_id is not None:
            db.delete_user(user_id)