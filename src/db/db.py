import sqlite3

def get_connect():
    connect = sqlite3.connect("tickets_system.db")
    return connect

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

            updated_at TEXT NOT NULL,
            due_at TEXT NOT NULL
        );
    '''

    agent_table = '''
        CREATE TABLE IF NOT EXISTS Agents (
            id TEXT PRIMARY KEY,
            nickname NOT NULL UNIQUE,
            avatar_url TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,

            created_at TEXT NOT NULL
            );
    '''

    # shouldnt we think that cilent.. is one of the agent role?
    #so create not separately clients/agents.. create users where you can put roles? 
    client_table = '''
        CREATE TABLE IF NOT EXISTS Clients (
            id TEXT PRIMARY KEY,
            nickname NOT NULL UNIQUE,
            avatar_url TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            );
    '''

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

            created_at TEXT NOT NULL
            )
    '''

    cursor.execute(tickets_table)
    cursor.execute(users_table)
    conn.commit()

def insert_data(data, table: str):
    conn = get_connect()
    cursor = conn.cursor()
    # can we do it easier? or have to write all tihngs by hand as 2-3 diffferent functions?
    match table:
        case "Users":
            insert_query = '''
                INSERT INTO Tickets (id, title, description, category, tags,
                                    assigned_agent_id, status, priority, updated_at, 
                                    created_at, due_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?);    
            '''
        case "Tickets":
            insert_query = '''
                INSERT INTO Users (id, nickname, avatar_url, first_name, last_name, 
                                    created_at, role, phone, email, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
            '''

    cursor.execute(data, insert_query)
    conn.commit()

def get_tickets(id: str | None = None) -> tuple:
    conn = get_connect()
    cursor = conn.cursor()

    if id:
        get_tickets = "SELECT * FROM Tickets WHERE id = id"
    else:
        get_tickets = "SELECT * FROM Tickets"

    cursor.execute(get_tickets)
    return cursor.fetchall()
    
def get_user_info(id: str) -> tuple:
    conn = get_connect()
    cursor = conn.cursor()

    get_info = "SELECT * FROM Users WHERE id = id"
    cursor.execute(get_info)
    return cursor.fetchone