import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
BOT_PREFIX = "lm!"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

MAX_HISTORY = _int_env("MAX_HISTORY", 16, 2)
MAX_OUTPUT_TOKENS = _int_env("MAX_OUTPUT_TOKENS", 768, 128)
MAX_INPUT_CHARS = _int_env("MAX_INPUT_CHARS", 6000, 500)
USER_COOLDOWN = _float_env("USER_COOLDOWN", 2.0, 0.0)
MAX_CONCURRENT_REQUESTS = _int_env("MAX_CONCURRENT_REQUESTS", 3, 1)
MAX_QUEUE_WAIT = _float_env("MAX_QUEUE_WAIT", 20.0, 1.0)
REQUEST_TIMEOUT = _float_env("REQUEST_TIMEOUT", 45.0, 5.0)
MEMORY_TTL_SECONDS = _int_env("MEMORY_TTL_SECONDS", 21600, 60)
MAX_CONVERSATIONS = _int_env("MAX_CONVERSATIONS", 500, 1)
MEMORY_PRUNE_INTERVAL = _int_env("MEMORY_PRUNE_INTERVAL", 900, 60)
COOLDOWN_PRUNE_INTERVAL = _int_env("COOLDOWN_PRUNE_INTERVAL", 3600, 60)
MAX_COOLDOWN_ENTRIES = _int_env("MAX_COOLDOWN_ENTRIES", 5000, 100)
DISCORD_MESSAGE_LIMIT = 2000
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
PORT = _int_env("PORT", 10000, 1)


def validate() -> None:
    missing: list[str] = []
    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    if not GEMINI_MODEL:
        raise RuntimeError("GEMINI_MODEL cannot be empty.")
    if GEMINI_THINKING_LEVEL not in {"minimal", "low", "medium", "high"}:
        raise RuntimeError("GEMINI_THINKING_LEVEL must be minimal, low, medium, or high.")
