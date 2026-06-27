import sqlite3
from src.models.models import Ticket, User

def get_connect():
    connect = sqlite3.connect("tickets_system.db")
    connect.row_factory = sqlite3.Row
    return connect

# ==========================================================================
# ======================= CREATING TABLES ==================================
def create_tables():
    conn = get_connect()
    cursor = conn.cursor()
    # sqlite ignores varchar length
    tickets_table = '''
        CREATE TABLE IF NOT EXISTS Tickets (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description NOT NULL,
            category TEXT NOT NULL,

            assigned_agent_id TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            tags TEXT NOT NULL,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            due_at TEXT NOT NULL
        );
    '''

    # agent and clients would be here
    users_table = '''
        CREATE TABLE IF NOT EXISTS Users(
            id TEXT PRIMARY KEY,
            nickname NOT NULL UNIQUE,
            avatar_url TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
            )
    '''

    cursor.execute(tickets_table)
    cursor.execute(users_table)
    conn.commit()


# ==========================================================================
# ============================ USERS =======================================

def insert_user(data: User):
    conn = get_connect()
    cursor = conn.cursor()
    insert_query = '''
        INSERT INTO Users (id, nickname, avatar_url, first_name, last_name, 
                            created_at, role, phone, email, created_at, updated_at)
        VALUES (:id, :nickname, :avatar_url, :first_name, :last_name, 
                :role, :phone, :email, :created_at, :updated_at);
        '''
    cursor.execute(insert_query, data)
    conn.commit()

def get_user(id: str) -> tuple:
    conn = get_connect()
    cursor = conn.cursor()

    get_info = "SELECT * FROM Users WHERE id = ?;"

    cursor.execute(get_info, (id,))
    conn.commit()
    return cursor.fetchone()

def get_users() -> tuple:
    conn = get_connect()
    cursor = conn.cursor()

    get_info = "SELECT * FROM Users;"
    cursor.execute(get_info)
    conn.commit()
    return cursor.fetchall()

def update_user(id: str, new_info: dict) -> int:
    conn = get_connect()
    cursor = conn.cursor()

    dynamic_params = ", ".join([f"{info} = ?" for info in new_info])

    values = list(new_info.values())
    values.append(id)
    query = f"UPDATE Users SET {dynamic_params} WHERE id = ?;"
    cursor.execute(query, values)

    conn.commit()
    return cursor.rowcount

def delete_user(id: str) -> int:
    conn = get_connect()
    cursor = conn.cursor()

    query = "DELETE FROM Users WHERE id = ?;"
    cursor.execute(query, (id,))
    conn.commit()
    return cursor.rowcount

# ==========================================================================
# ============================ TICKETS =====================================

def insert_ticket(data: Ticket):
    conn = get_connect()
    cursor = conn.cursor()
    insert_query = '''
        INSERT INTO Tickets (id, title, description, category, tags,
                            assigned_agent_id, status, priority, updated_at, 
                            created_at, due_at) 
        VALUES(:id, :title, :description, :category, :tags,
                            :assigned_agent_id, :status, :priority, :updated_at, 
                            :created_at, :due_at);    
        '''
    
    cursor.execute(insert_query, data)
    conn.commit()

def get_tickets() -> tuple:
    conn = get_connect()
    cursor = conn.cursor()

    get_tickets = "SELECT * FROM Tickets;"
    cursor.execute(get_tickets) 
    conn.commit()
    return cursor.fetchall()

def get_ticket(id: str):
    conn = get_connect()
    cursor = conn.cursor()

    get_tickets = "SELECT * FROM Tickets WHERE id = ?;"
    cursor.execute(get_tickets, (id,))
    conn.commit()
    return cursor.fetchone()

def update_ticket(id: str, new_info: dict) -> int:
    conn = get_connect()
    cursor = conn.cursor()


    # have to do.. dynamic query. i dont wanna do robust validation etc right now, can add it later (cuz we also have to check
    # the rights of the user)

    dynamic_params = ", ".join([f"{key} = ?"for key in new_info.keys()])
    query = f"UPDATE Tickets SET {dynamic_params} WHERE id = ?;"

    values = list(new_info.values())
    values.append(id)
    cursor.execute(query, values)
    conn.commit()
    return cursor.rowcount

def delete_ticket(id: str) -> int:
    conn = get_connect()
    cursor = conn.cursor()

    query = f"DELETE FROM Tickets WHERE id = ?;"
    cursor.execute(query, (id,))
    conn.commit()

    return cursor.rowcount