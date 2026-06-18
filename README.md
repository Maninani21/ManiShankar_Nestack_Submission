# Webhook Delivery Engine

A backend system that accepts events, delivers them via HTTP POST to customer webhook URLs, retries on failure, and exposes endpoints to inspect delivery status.

## Tech Stack

- **Python 3.10+**
- **Flask** — API server
- **SQLite** — persistent storage
- **threading** — background delivery worker (no queue library used)
- **requests** — HTTP delivery
- **hmac + hashlib** — HMAC-SHA256 request signing

---

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd webhook_engine
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Set environment variables

```bash
export WEBHOOK_SIGNING_KEY="your-secret-signing-key"
export DATABASE_PATH="webhook_engine.db"
```

If not set, defaults are used (`my-super-secret-key-2024` and `webhook_engine.db`).

---

## Running the Server

The API server and the background delivery worker start together with a single command:

```bash
python app.py
```

You should see:

```
[Worker] Delivery engine started.
[App] Starting webhook delivery engine...
 * Running on http://0.0.0.0:5000
```

The worker polls for due events every 5 seconds in a background thread.

---

## API Endpoints

### POST `/events` — Ingest a new event

```bash
curl -X POST http://localhost:5000/events \
  -H "Content-Type: application/json" \
  -d '{
    "type": "payment.failed",
    "payload": {"amount": 100, "currency": "USD"},
    "webhook_url": "https://your-server.com/webhook"
  }'
```

**Response (201):**
```json
{
  "id": "uuid",
  "type": "payment.failed",
  "payload": {"amount": 100, "currency": "USD"},
  "webhook_url": "https://your-server.com/webhook",
  "status": "pending",
  "created_at": "2024-01-01T00:00:00",
  "attempts": []
}
```

---

### GET `/events` — List all events

```bash
curl http://localhost:5000/events
```

---

### GET `/events/:id` — Get event with full attempt history

```bash
curl http://localhost:5000/events/<event-id>
```

**Response includes attempts array:**
```json
{
  "id": "uuid",
  "status": "failed",
  "attempts": [
    {
      "attempted_at": "2024-01-01T00:00:00",
      "http_status": 500,
      "outcome": "failed"
    }
  ]
}
```

---

### POST `/events/:id/retry` — Manually retry a dead event

```bash
curl -X POST http://localhost:5000/events/<event-id>/retry
```

Returns `400` if the event is not in `dead` status.

---

## HMAC Signature Verification

Every outgoing webhook request includes an `X-Webhook-Signature` header.

**Format:** `sha256=<hex-digest>`

### How it is generated

The signature is computed over the JSON-serialized request body using HMAC-SHA256:

```python
import hmac, hashlib, json

def verify_signature(payload: dict, signature_header: str, secret: str) -> bool:
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```

### How to verify on your server

```python
from flask import request

SECRET = "my-super-secret-key-2024"

@app.route("/webhook", methods=["POST"])
def receive_webhook():
    signature = request.headers.get("X-Webhook-Signature", "")
    body = request.get_json()
    
    if not verify_signature(body, signature, SECRET):
        return "Invalid signature", 401
    
    # Process the event
    print("Event received:", body["type"])
    return "OK", 200
```

**Signing key:** Set via the `WEBHOOK_SIGNING_KEY` environment variable. Default: `my-super-secret-key-2024`.

---

## Retry Schedule

| Attempt | Trigger |
|---------|---------|
| 1st | Immediately on ingestion |
| 2nd | 30 seconds after failure |
| 3rd | 5 minutes after 2nd failure |
| 4th | 30 minutes after 3rd failure |
| Dead | After 4th failure, no more retries |

Retry scheduling is implemented directly using `datetime` arithmetic and a polling loop — **no queue library (Celery, BullMQ, RQ, etc.) is used**.

---

## Server Restart Behavior

**Does the implementation survive restarts?**

Yes — partially. Because SQLite is used as persistent storage:

- All events and their attempt history are preserved across restarts.
- Events in `pending` or `failed` status with a `next_attempt_at` in the past will be picked up by the worker immediately after restart.

**What is lost on restart:**

- Any event that was mid-delivery (HTTP request in-flight) at the exact moment of crash will not have its attempt logged. It will be retried on restart since its status is still `pending` or `failed`.
- The in-memory retry timer is not preserved — but since `next_attempt_at` is stored in SQLite, the worker recalculates correctly on startup.

**In summary:** The system is resilient to restarts. No events are permanently lost, and retries resume automatically.

---

## Deployment

Live deployment: `<your-deployment-url>`

To deploy on a server:

```bash
pip install gunicorn
gunicorn -w 1 app:app --bind 0.0.0.0:8000
```

> Use `-w 1` (single worker) to ensure only one background delivery thread runs.