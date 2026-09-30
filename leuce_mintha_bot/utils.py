import re
import time
from collections.abc import Iterable

from .config import DISCORD_MESSAGE_LIMIT, MAX_COOLDOWN_ENTRIES


class CooldownManager:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last: dict[int, float] = {}

    def consume(self, user_id: int) -> float:
        now = time.monotonic()
        previous = self._last.get(user_id)
        if previous is not None:
            remaining = self.seconds - (now - previous)
            if remaining > 0:
                return remaining
        self._last[user_id] = now
        self._enforce_limit()
        return 0.0

    def prune(self, older_than: float) -> int:
        cutoff = time.monotonic() - older_than
        stale = [uid for uid, ts in self._last.items() if ts < cutoff]
        for uid in stale:
            self._last.pop(uid, None)
        return len(stale)

    def _enforce_limit(self) -> None:
        overflow = len(self._last) - MAX_COOLDOWN_ENTRIES
        if overflow <= 0:
            return
        oldest = sorted(self._last.items(), key=lambda item: item[1])[:overflow]
        for uid, _ in oldest:
            self._last.pop(uid, None)


def contains_bot_mention(content: str, bot_id: int) -> bool:
    return re.search(rf"<@!?{re.escape(str(bot_id))}>", content) is not None


def strip_bot_mentions(content: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{re.escape(str(bot_id))}>", " ", content)


def strip_typed_name(content: str, names: Iterable[str]) -> tuple[str, bool]:
    found = False
    for name in names:
        if not name:
            continue
        pattern = re.compile(rf"@{re.escape(name)}(?=\s|$)", re.IGNORECASE)
        content, count = pattern.subn(" ", content, count=1)
        if count:
            found = True
            break
    return content, found


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    text = text.strip()
    if not text:
        return ["..."]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    return chunks
