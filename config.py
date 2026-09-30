import os

from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    GEMINI_MODEL = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )
    # Fixed prefix for this bot so it cannot conflict with the existing Hades bot.
    BOT_PREFIX = "lm!"

    MAX_HISTORY = env_int("MAX_HISTORY", 16)
    MAX_OUTPUT_TOKENS = env_int("MAX_OUTPUT_TOKENS", 768)
    USER_COOLDOWN = env_float("USER_COOLDOWN", 2.0)
    MAX_CONCURRENT_REQUESTS = env_int("MAX_CONCURRENT_REQUESTS", 3)
    REQUEST_TIMEOUT = env_int("REQUEST_TIMEOUT", 45)
    MEMORY_TTL_SECONDS = env_int("MEMORY_TTL_SECONDS", 21600)
    MAX_CONVERSATIONS = env_int("MAX_CONVERSATIONS", 500)
    MAX_INPUT_CHARS = env_int("MAX_INPUT_CHARS", 12000)

    PORT = env_int("PORT", 10000)
