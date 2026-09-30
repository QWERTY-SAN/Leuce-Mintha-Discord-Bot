import os
import threading

from flask import Flask, jsonify

app = Flask(__name__)
_state = {"discord_ready": False, "discord_user": None, "guild_count": 0}
_state_lock = threading.Lock()


def update_discord_state(*, ready: bool, user: str | None = None, guild_count: int = 0) -> None:
    with _state_lock:
        _state["discord_ready"] = ready
        _state["discord_user"] = user
        _state["guild_count"] = guild_count


def _snapshot() -> dict:
    with _state_lock:
        return dict(_state)


@app.get("/")
def index():
    state = _snapshot()
    return jsonify({
        "service": "Leuce & Mintha Discord AI",
        "status": "online" if state["discord_ready"] else "starting",
        **state,
    })


@app.get("/health")
def health():
    return jsonify({"service": "leuce-mintha-discord-bot", "status": "ok", **_snapshot()}), 200


@app.get("/ready")
def ready():
    state = _snapshot()
    code = 200 if state["discord_ready"] else 503
    return jsonify({
        "service": "leuce-mintha-discord-bot",
        "status": "ready" if state["discord_ready"] else "not-ready",
        **state,
    }), code


def run_web_server() -> None:
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def start_web_server() -> threading.Thread:
    thread = threading.Thread(target=run_web_server, name="render-health-server", daemon=True)
    thread.start()
    return thread
