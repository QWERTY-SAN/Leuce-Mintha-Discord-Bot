import re
import time

from .config import DISCORD_MESSAGE_LIMIT, MAX_COOLDOWN_ENTRIES


class CooldownManager:
    def __init__(self, cooldown_seconds: float) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._last_request: dict[int, float] = {}

    def consume(self, user_id: int) -> float:
        now = time.monotonic()
        previous = self._last_request.get(user_id, 0.0)
        remaining = self.cooldown_seconds - (now - previous)
        if remaining > 0:
            return remaining
        self._last_request[user_id] = now
        self._enforce_limit()
        return 0.0

    def prune(self, older_than_seconds: float = 3600.0) -> int:
        cutoff = time.monotonic() - older_than_seconds
        stale = [
            user_id
            for user_id, timestamp in self._last_request.items()
            if timestamp < cutoff
        ]
        for user_id in stale:
            self._last_request.pop(user_id, None)
        return len(stale)

    def size(self) -> int:
        return len(self._last_request)

    def _enforce_limit(self) -> None:
        if len(self._last_request) <= MAX_COOLDOWN_ENTRIES:
            return
        oldest = sorted(self._last_request.items(), key=lambda item: item[1])
        for user_id, _ in oldest[: len(self._last_request) - MAX_COOLDOWN_ENTRIES]:
            self._last_request.pop(user_id, None)


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    text = text.strip()
    if not text:
        return ["..."]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n\n", 0, limit)
        if split_at < 1:
            split_at = text.rfind("\n", 0, limit)
        if split_at < 1:
            split_at = text.rfind(" ", 0, limit)
        if split_at < 1:
            split_at = limit
        chunk = text[:split_at].rstrip()
        if chunk:
            chunks.append(chunk)
        text = text[split_at:].lstrip()

    if text:
        chunks.append(text)
    return chunks


def strip_bot_mentions(content: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{re.escape(str(bot_id))}>", "", content).strip()


def contains_bot_mention(content: str, bot_id: int) -> bool:
    return re.search(rf"<@!?{re.escape(str(bot_id))}>", content) is not None
