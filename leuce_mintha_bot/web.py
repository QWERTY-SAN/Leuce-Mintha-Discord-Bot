import os
import threading

from flask import Flask, jsonify

app = Flask(__name__)
_state = {"discord_ready": False, "discord_user": None, "guild_count": 0}
_lock = threading.Lock()


def update_discord_state(*, ready: bool, user: str | None = None, guild_count: int = 0) -> None:
    with _lock:
        _state.update({"discord_ready": ready, "discord_user": user, "guild_count": guild_count})


def _snapshot() -> dict:
    with _lock:
        return dict(_state)


@app.get("/")
def index():
    state = _snapshot()
    return jsonify({
        "service": "Leuce & Mintha Discord AI",
        "status": "online" if state["discord_ready"] else "starting",
        "game": "Aether Gazer",
        **state,
    })


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "leuce-mintha-discord-bot", **_snapshot()}), 200


@app.get("/ready")
def ready():
    state = _snapshot()
    return jsonify({
        "status": "ready" if state["discord_ready"] else "not-ready",
        "service": "leuce-mintha-discord-bot",
        **state,
    }), 200 if state["discord_ready"] else 503


def start_web_server() -> threading.Thread:
    thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            debug=False,
            use_reloader=False,
            threaded=True,
        ),
        name="health-server",
        daemon=True,
    )
    thread.start()
    return thread
