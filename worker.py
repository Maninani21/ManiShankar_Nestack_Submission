import time
import requests
import json
import hmac
import hashlib
import threading
from datetime import datetime, timedelta
import database
from config import SECRET_KEY, RETRY_INTERVALS, TIMEOUT


# generate hmac signature for the request
def sign(payload):
    data = json.dumps(payload, separators=(',', ':')).encode()
    h = hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
    return "sha256=" + h


def try_deliver(event):
    id = event["id"]
    
    body = {
        "event_id": id,
        "type": event["type"],
        "payload": event["payload"],
        "created_at": event["created_at"]
    }

    sig = sign(body)

    # set headers
    headers = {}
    headers["Content-Type"] = "application/json"
    headers["X-Webhook-Signature"] = sig

    status_code = None
    success = False

    try:
        res = requests.post(event["webhook_url"], json=body, headers=headers, timeout=TIMEOUT)
        status_code = res.status_code
        print("got response:", status_code)

        if status_code >= 200 and status_code < 300:
            success = True

    except requests.exceptions.Timeout:
        print("request timed out for event", id)
        success = False
    except Exception as e:
        print("some error occured:", e)
        success = False

    # save this attempt
    if success:
        database.save_attempt(id, status_code, "success")
        database.update_status(id, "delivered")
        print("delivered event", id)
    else:
        database.save_attempt(id, status_code, "failed")

        # check how many times we tried
        total_attempts = database.count_attempts(id)
        print("total attempts so far:", total_attempts)

        if total_attempts <= len(RETRY_INTERVALS):
            # schedule next retry
            wait = RETRY_INTERVALS[total_attempts - 1]
            next_time = datetime.utcnow() + timedelta(seconds=wait)
            database.update_status(id, "failed", next_time.isoformat())
            print("will retry after", wait, "seconds")
        else:
            # give up
            database.update_status(id, "dead")
            print("event", id, "is dead now")


# main worker loop
def worker_loop():
    print("worker started...")
    while True:
        try:
            events = database.get_due_events()
            if len(events) > 0:
                print("found", len(events), "events to process")
            for e in events:
                try_deliver(e)
        except Exception as err:
            print("worker error:", err)

        time.sleep(5)  # check every 5 seconds


def start():
    t = threading.Thread(target=worker_loop)
    t.daemon = True
    t.start()
    print("worker thread started")