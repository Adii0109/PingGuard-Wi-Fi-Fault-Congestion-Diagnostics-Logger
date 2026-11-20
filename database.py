import os
from datetime import date, timedelta
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "my_python_app")


def get_server_connection():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD
    )


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )


def init_and_clean_database():
    """Checks if DB exists, creates if missing, sets up PingGuard table, and clears >7 days."""
    conn = get_server_connection()
    cursor = conn.cursor()

    cursor.execute("SHOW DATABASES LIKE %s", (DB_NAME,))
    if cursor.fetchone():
        print(f"[INFO] Database '{DB_NAME}' found. Using existing database.")
    else:
        cursor.execute(f"CREATE DATABASE `{DB_NAME}`")
        print(f"[INFO] Database '{DB_NAME}' created.")

    cursor.close()
    conn.close()

    db_conn = get_db_connection()
    db_cursor = db_conn.cursor()

    db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS pingguard_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            log_date DATE NOT NULL,
            session_id VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL,
            ping_ms FLOAT NOT NULL,
            details TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_day_session (log_date, session_id)
        )
    """)

    # Auto-clear records older than 7 days
    cutoff_date = date.today() - timedelta(days=7)
    db_cursor.execute("DELETE FROM pingguard_logs WHERE log_date < %s", (cutoff_date,))
    db_conn.commit()
    db_cursor.close()
    db_conn.close()


def add_pingguard_record(session_id, status, ping_ms, details, now_dt):
    """Saves a PingGuard telemetry event into MySQL under today's date and session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pingguard_logs (log_date, session_id, status, ping_ms, details, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (now_dt.date(), session_id, status, ping_ms, details, now_dt))
    conn.commit()
    cursor.close()
    conn.close()


def get_available_days():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT log_date FROM pingguard_logs ORDER BY log_date DESC")
    days = [row[0].strftime("%Y-%m-%d") for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return days

def get_records_by_day(selected_day):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, log_date, session_id, status, ping_ms, details, created_at
        FROM pingguard_logs
        WHERE log_date = %s
        ORDER BY session_id ASC, created_at ASC
    """, (selected_day,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    grouped = {}
    for row in rows:
        row["log_date"] = row["log_date"].strftime("%Y-%m-%d")
        row["time_logged"] = row["created_at"].strftime("%H:%M:%S")
        del row["created_at"]
        sess = row["session_id"]
        if sess not in grouped:
            grouped[sess] = []
        grouped[sess].append(row)
    return grouped
