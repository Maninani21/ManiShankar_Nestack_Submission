import sqlite3
import json
import uuid
from datetime import datetime
from config import DATABASE_PATH


def get_connection():
    """Create and return a new database connection."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # allows dict-like access to rows
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            webhook_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            next_attempt_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            http_status INTEGER,
            outcome TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
    """)

    conn.commit()
    conn.close()


def create_event(event_type, payload, webhook_url):
    """Insert a new event into the database and return it."""
    event_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO events (id, type, payload, webhook_url, status, created_at, next_attempt_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?)
    """, (event_id, event_type, json.dumps(payload), webhook_url, created_at, created_at))

    conn.commit()
    conn.close()

    return get_event_by_id(event_id)


def get_all_events():
    """Return all events with their attempts."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    return [_format_event(row) for row in rows]


def get_event_by_id(event_id):
    """Return a single event with its full attempts history."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return None

    event = _format_event(row)

    cursor.execute(
        "SELECT * FROM attempts WHERE event_id = ? ORDER BY attempted_at ASC",
        (event_id,)
    )
    attempt_rows = cursor.fetchall()
    conn.close()

    event["attempts"] = [
        {
            "attempted_at": a["attempted_at"],
            "http_status": a["http_status"],
            "outcome": a["outcome"]
        }
        for a in attempt_rows
    ]

    return event


def get_pending_events_due_now():
    """Return all pending/failed events whose next_attempt_at is due."""
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM events
        WHERE status IN ('pending', 'failed')
        AND next_attempt_at <= ?
    """, (now,))
    rows = cursor.fetchall()
    conn.close()

    return [_format_event(row) for row in rows]


def log_attempt(event_id, http_status, outcome):
    """Record a delivery attempt for an event."""
    attempt_id = str(uuid.uuid4())
    attempted_at = datetime.utcnow().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO attempts (id, event_id, attempted_at, http_status, outcome)
        VALUES (?, ?, ?, ?, ?)
    """, (attempt_id, event_id, attempted_at, http_status, outcome))

    conn.commit()
    conn.close()


def update_event_status(event_id, status, next_attempt_at=None):
    """Update the status and optionally the next retry time of an event."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE events
        SET status = ?, next_attempt_at = ?
        WHERE id = ?
    """, (status, next_attempt_at, event_id))

    conn.commit()
    conn.close()


def count_attempts(event_id):
    """Return the number of attempts made for an event."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM attempts WHERE event_id = ?", (event_id,))
    count = cursor.fetchone()[0]
    conn.close()

    return count


def requeue_dead_event(event_id):
    """Reset a dead event back to pending so the worker picks it up."""
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE events
        SET status = 'pending', next_attempt_at = ?
        WHERE id = ? AND status = 'dead'
    """, (now, event_id))

    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0


def _format_event(row):
    """Convert a database row to a dict."""
    return {
        "id": row["id"],
        "type": row["type"],
        "payload": json.loads(row["payload"]),
        "webhook_url": row["webhook_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "attempts": []
    }