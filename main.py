import threading

from flask import Flask, jsonify

from bot import LeuceMinthaBot
from config import Config

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify(
        {
            "status": "online",
            "service": "Leuce & Mintha Discord AI",
            "game": "Aether Gazer",
            "model": Config.GEMINI_MODEL,
        }
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


def run_health_server() -> None:
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=False,
        use_reloader=False,
    )


def main() -> None:
    if not Config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set.")
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    health_thread = threading.Thread(
        target=run_health_server,
        name="health-server",
        daemon=True,
    )
    health_thread.start()

    bot = LeuceMinthaBot()
    print("Starting Leuce & Mintha with fixed prefix: lm!")
    bot.run(Config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
