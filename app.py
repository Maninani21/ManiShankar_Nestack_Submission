from flask import Flask, request, jsonify
import database
import worker

app = Flask(__name__)


@app.route("/events", methods=["POST"])
def ingest_event():
    """
    Accept a new event and queue it for delivery.
    Body: { type, payload, webhook_url }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    missing = [f for f in ["type", "payload", "webhook_url"] if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    event = database.create_event(
        event_type=data["type"],
        payload=data["payload"],
        webhook_url=data["webhook_url"]
    )

    return jsonify(event), 201


@app.route("/events", methods=["GET"])
def list_events():
    """Return all events (without full attempt history for brevity)."""
    events = database.get_all_events()
    return jsonify(events), 200


@app.route("/events/<event_id>", methods=["GET"])
def get_event(event_id):
    """Return a single event with its full attempt history."""
    event = database.get_event_by_id(event_id)

    if event is None:
        return jsonify({"error": "Event not found"}), 404

    return jsonify(event), 200


@app.route("/events/<event_id>/retry", methods=["POST"])
def retry_event(event_id):
    """
    Manually re-queue a dead event for redelivery.
    Returns 400 if the event is not in dead status.
    """
    event = database.get_event_by_id(event_id)

    if event is None:
        return jsonify({"error": "Event not found"}), 404

    if event["status"] != "dead":
        return jsonify({
            "error": "Only dead events can be manually retried",
            "current_status": event["status"]
        }), 400

    requeued = database.requeue_dead_event(event_id)

    if requeued:
        updated_event = database.get_event_by_id(event_id)
        return jsonify({
            "message": "Event re-queued for delivery",
            "event": updated_event
        }), 200

    return jsonify({"error": "Could not re-queue event"}), 500


if __name__ == "__main__":
    # Initialize database tables
    database.init_db()

    # Start background delivery worker
    worker.start_worker_thread()

    print("[App] Starting webhook delivery engine...")
    app.run(host="0.0.0.0", port=5000, debug=False)