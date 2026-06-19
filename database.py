import sqlite3
import uuid
import json
from datetime import datetime
from config import DB


# connecting to db
def connect():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


# creating tables if not exist
def init_db():
    con = connect()
    cur = con.cursor()

    # events table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT,
            type TEXT,
            payload TEXT,
            webhook_url TEXT,
            status TEXT,
            created_at TEXT,
            next_attempt_at TEXT
        )
    """)

    # attempts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT,
            event_id TEXT,
            attempted_at TEXT,
            http_status INTEGER,
            outcome TEXT
        )
    """)

    con.commit()
    con.close()
    print("db initialized")


def add_event(type, payload, url):
    id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    con = connect()
    cur = con.cursor()
    cur.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                (id, type, json.dumps(payload), url, "pending", now, now))
    con.commit()
    con.close()

    # return the event we just created
    return get_event(id)


def get_all():
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM events")
    rows = cur.fetchall()
    con.close()

    result = []
    for r in rows:
        result.append(make_event_dict(r))
    return result


def get_event(id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM events WHERE id=?", (id,))
    row = cur.fetchone()

    if row == None:
        con.close()
        return None

    event = make_event_dict(row)

    # also get attempts
    cur.execute("SELECT * FROM attempts WHERE event_id=?", (id,))
    attempts = cur.fetchall()
    con.close()

    alist = []
    for a in attempts:
        alist.append({
            "attempted_at": a["attempted_at"],
            "http_status": a["http_status"],
            "outcome": a["outcome"]
        })
    event["attempts"] = alist

    return event


# get events that need to be delivered now
def get_due_events():
    now = datetime.utcnow().isoformat()
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM events WHERE status=? OR status=?", ("pending", "failed"))
    rows = cur.fetchall()
    con.close()

    due = []
    for r in rows:
        if r["next_attempt_at"] <= now:
            due.append(make_event_dict(r))
    return due


def save_attempt(event_id, http_status, outcome):
    id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    con = connect()
    cur = con.cursor()
    cur.execute("INSERT INTO attempts VALUES (?,?,?,?,?)",
                (id, event_id, now, http_status, outcome))
    con.commit()
    con.close()


def update_status(event_id, status, next_time=None):
    con = connect()
    cur = con.cursor()
    cur.execute("UPDATE events SET status=?, next_attempt_at=? WHERE id=?",
                (status, next_time, event_id))
    con.commit()
    con.close()


def count_attempts(event_id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM attempts WHERE event_id=?", (event_id,))
    c = cur.fetchone()[0]
    con.close()
    return c


def requeue(event_id):
    con = connect()
    cur = con.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("UPDATE events SET status='pending', next_attempt_at=? WHERE id=? AND status='dead'",
                (now, event_id))
    rows_updated = cur.rowcount
    con.commit()
    con.close()
    if rows_updated > 0:
        return True
    return False


def make_event_dict(r):
    return {
        "id": r["id"],
        "type": r["type"],
        "payload": json.loads(r["payload"]),
        "webhook_url": r["webhook_url"],
        "status": r["status"],
        "created_at": r["created_at"],
        "attempts": []
    }