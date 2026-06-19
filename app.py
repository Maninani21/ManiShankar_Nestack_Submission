from flask import Flask, request, jsonify
import database
import worker

app = Flask(__name__)


@app.route("/events", methods=["POST"])
def create_event():
    data = request.get_json()

    # basic validation
    if data is None:
        return jsonify({"error": "send json data"}), 400

    if "type" not in data:
        return jsonify({"error": "type is required"}), 400

    if "payload" not in data:
        return jsonify({"error": "payload is required"}), 400

    if "webhook_url" not in data:
        return jsonify({"error": "webhook_url is required"}), 400

    e = database.add_event(data["type"], data["payload"], data["webhook_url"])
    return jsonify(e), 201


@app.route("/events", methods=["GET"])
def list_events():
    events = database.get_all()
    return jsonify(events), 200


@app.route("/events/<id>", methods=["GET"])
def get_event(id):
    e = database.get_event(id)

    if e is None:
        return jsonify({"error": "event not found"}), 404

    return jsonify(e), 200


@app.route("/events/<id>/retry", methods=["POST"])
def retry_event(id):
    e = database.get_event(id)

    if e is None:
        return jsonify({"error": "not found"}), 404

    # only dead events can be retried
    if e["status"] != "dead":
        return jsonify({"error": "event is not dead, cannot retry"}), 400

    done = database.requeue(id)

    if done:
        return jsonify({"message": "ok event requeued", "event": database.get_event(id)}), 200
    else:
        return jsonify({"error": "something went wrong"}), 500


if __name__ == "__main__":
    database.init_db()
    worker.start()
    print("starting server...")
    app.run(host="0.0.0.0", port=5000, debug=False)