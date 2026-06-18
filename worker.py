import time
import hmac
import hashlib
import json
import threading
import requests
from datetime import datetime, timedelta

from config import SIGNING_KEY, RETRY_INTERVALS, REQUEST_TIMEOUT
import database


def generate_signature(payload: dict) -> str:
    """
    Generate HMAC-SHA256 signature for the outgoing webhook payload.
    The signature is computed over the JSON-serialized payload string.
    """
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        SIGNING_KEY.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


def deliver_event(event: dict):
    """
    Attempt to deliver a single event via HTTP POST.
    Logs the attempt and updates the event status accordingly.
    """
    event_id = event["id"]
    payload = event["payload"]
    webhook_url = event["webhook_url"]

    # Build the outgoing request body
    body = {
        "event_id": event_id,
        "type": event["type"],
        "payload": payload,
        "created_at": event["created_at"]
    }

    signature = generate_signature(body)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature
    }

    http_status = None
    outcome = "failed"

    try:
        response = requests.post(
            webhook_url,
            json=body,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        http_status = response.status_code

        if 200 <= http_status < 300:
            outcome = "success"

    except requests.exceptions.Timeout:
        # Timeout counts as failure, http_status stays None
        outcome = "failed"
    except requests.exceptions.RequestException:
        # Any connection error counts as failure
        outcome = "failed"

    # Log this attempt in the database
    database.log_attempt(event_id, http_status, outcome)

    if outcome == "success":
        database.update_event_status(event_id, "delivered")
        print(f"[Worker] Event {event_id} delivered successfully.")
        return

    # Delivery failed — check how many attempts have been made
    attempt_count = database.count_attempts(event_id)

    # attempt_count includes the one we just logged
    # We allow up to 4 total attempts (1 initial + 3 retries)
    if attempt_count <= len(RETRY_INTERVALS):
        # Schedule the next retry
        interval_seconds = RETRY_INTERVALS[attempt_count - 1]
        next_attempt_at = (
            datetime.utcnow() + timedelta(seconds=interval_seconds)
        ).isoformat()
        database.update_event_status(event_id, "failed", next_attempt_at)
        print(
            f"[Worker] Event {event_id} failed (attempt {attempt_count}). "
            f"Retrying in {interval_seconds}s."
        )
    else:
        # Exceeded max retries — mark as dead
        database.update_event_status(event_id, "dead")
        print(f"[Worker] Event {event_id} is now dead after {attempt_count} attempts.")


def run_worker():
    """
    Background loop that continuously polls for pending/failed events
    and attempts delivery when they are due.
    """
    print("[Worker] Delivery engine started.")
    while True:
        try:
            due_events = database.get_pending_events_due_now()

            for event in due_events:
                # Temporarily mark as 'processing' to avoid double-pickup
                # We do this by setting next_attempt_at far in the future
                # while we attempt delivery
                deliver_event(event)

        except Exception as e:
            print(f"[Worker] Unexpected error: {e}")

        # Poll every 5 seconds
        time.sleep(5)


def start_worker_thread():
    """Start the worker in a daemon background thread."""
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    return thread