# Webhook Delivery Engine

This is my submission for the Nestack SDE assessment. I built a webhook delivery system using Python and Flask.

## Live Deployment
https://manishankar-nestack-submission-vfvp.onrender.com

## What it does
When an event comes in (like payment.failed or user.signup), the system saves it and tries to deliver it to the customer's webhook URL. If delivery fails it will retry automatically. Customers can also check status of their events.

## Tech used
- Python
- Flask
- SQLite
- requests library

## How to run locally

first clone the repo
```
git clone https://github.com/Maninani21/ManiShankar_Nestack_Submission.git
cd ManiShankar_Nestack_Submission
```

create virtual environment and install packages
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

start the server
```
python app.py
```

server will start on http://localhost:5000

## API Endpoints

**POST /events** - create a new event
```
POST /events
{
    "type": "payment.failed",
    "payload": {"amount": 100},
    "webhook_url": "https://your-server.com/webhook"
}
```

**GET /events** - get all events
```
GET /events
```

**GET /events/:id** - get single event with attempts
```
GET /events/some-event-id
```

**POST /events/:id/retry** - retry a dead event
```
POST /events/some-event-id/retry
```

## Retry Schedule

| Attempt | When |
|---------|------|
| 1st attempt | immediately |
| 2nd attempt | after 30 seconds |
| 3rd attempt | after 5 minutes |
| 4th attempt | after 30 minutes |
| after 4th fail | marked as dead |

I implemented the retry logic myself without using any queue library. I used datetime to calculate next retry time and stored it in database. Background worker checks every 5 seconds for due events.

## HMAC Signature

Every outgoing request has a X-Webhook-Signature header. It is generated using HMAC-SHA256.

signing key is: `mywebhooksecret123`

How to verify on your server:
```python
import hmac, hashlib, json

def verify(payload, signature):
    secret = "mywebhooksecret123"
    body = json.dumps(payload, separators=(',', ':')).encode()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## What happens on server restart

Since I am using SQLite the data is saved on disk so events are not lost on restart. When server starts again the worker will pick up any pending or failed events automatically and continue retrying them.

However if a request was in the middle of being sent when server crashed, that attempt wont be logged but the event will still be retried since status is still pending or failed in database.