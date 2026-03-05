import sqlite3
from config import DB_NAME
from datetime import datetime


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,              -- expense | income | debt
            amount REAL,
            description TEXT,
            person TEXT,
            created_at TEXT
        )
        """)

        conn.commit()


def add_transaction(user_id, t_type, amount, description="", person=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO transactions (user_id, type, amount, description, person, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            t_type,
            amount,
            description,
            person,
            datetime.now().isoformat()
        ))
        conn.commit()


def get_transactions(user_id, start_date=None, end_date=None, t_type=None):
    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT type, amount, description, person, created_at FROM transactions WHERE user_id=?"
        params = [user_id]

        if t_type:
            query += " AND type=?"
            params.append(t_type)

        if start_date:
            query += " AND date(created_at) >= date(?)"
            params.append(start_date)

        if end_date:
            query += " AND date(created_at) <= date(?)"
            params.append(end_date)

        cursor.execute(query, params)
        return cursor.fetchall()