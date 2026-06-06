import sqlite3
import logging
from pathlib import Path

# Absolute path to ensure DB is created in the correct folder
DATABASE_FILE = Path(__file__).parent / "bot_data.db"

def _get_connection():
    return sqlite3.connect(DATABASE_FILE, timeout=30)

def initialize_db():
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_blocked INTEGER DEFAULT 0,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS queries (
                query_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query_text TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        con.commit()
        con.close()
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

def add_user_if_not_exists(user_id: int, username: str, first_name: str):
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name)
            )
            con.commit()
        con.close()
    except Exception as e:
        logging.error(f"Error adding user {user_id}: {e}")

def log_query(user_id: int, query_text: str):
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO queries (user_id, query_text) VALUES (?, ?)",
            (user_id, query_text)
        )
        con.commit()
        con.close()
    except Exception as e:
        logging.error(f"Error logging query for user {user_id}: {e}")

def is_user_blocked(user_id: int) -> bool:
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        con.close()
        return result[0] == 1 if result else False
    except Exception as e:
        return False

def set_user_blocked_status(user_id: int, is_blocked: bool):
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (1 if is_blocked else 0, user_id))
        con.commit()
        con.close()
    except Exception as e:
        logging.error(f"Error blocking user {user_id}: {e}")

# --- New Admin Stats Functions ---
def get_stats():
    try:
        con = _get_connection()
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM queries")
        query_count = cur.fetchone()[0]
        con.close()
        return user_count, query_count
    except Exception as e:
        logging.error(f"Error getting stats: {e}")
        return 0, 0

# ... keep all previous functions ...

def get_detailed_stats():
    """Returns a list of tuples: (first_name, username, message_count)"""
    try:
        con = _get_connection()
        cur = con.cursor()
        # SQL Magic: Count queries per user and sort by most active
        cur.execute('''
            SELECT u.first_name, u.username, COUNT(q.query_id) as msg_count
            FROM users u
            LEFT JOIN queries q ON u.user_id = q.user_id
            GROUP BY u.user_id
            ORDER BY msg_count DESC
            LIMIT 50
        ''')
        rows = cur.fetchall()
        con.close()
        return rows
    except Exception as e:
        logging.error(f"Error getting detailed stats: {e}")
        return []
