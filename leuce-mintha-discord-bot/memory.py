import time
from collections import OrderedDict
from typing import TypeAlias

ConversationKey: TypeAlias = tuple[int, int]
MessageTurn: TypeAlias = tuple[str, str]


class ConversationMemory:
    def __init__(
        self,
        max_history: int,
        ttl_seconds: int,
        max_conversations: int,
    ) -> None:
        self.max_history = max_history
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self._data: OrderedDict[
            ConversationKey,
            tuple[float, list[MessageTurn]],
        ] = OrderedDict()

    def _expired(self, timestamp: float) -> bool:
        return (time.monotonic() - timestamp) > self.ttl_seconds

    def get(self, key: ConversationKey) -> list[MessageTurn]:
        item = self._data.get(key)
        if item is None:
            return []

        timestamp, history = item
        if self._expired(timestamp):
            self._data.pop(key, None)
            return []

        self._data.move_to_end(key)
        self._data[key] = (time.monotonic(), history)
        return list(history)

    def add_turn(self, key: ConversationKey, role: str, text: str) -> None:
        history = self.get(key)
        history.append((role, text))
        if len(history) > self.max_history:
            history = history[-self.max_history:]

        self._data[key] = (time.monotonic(), history)
        self._data.move_to_end(key)

        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)

    def clear(self, key: ConversationKey) -> None:
        self._data.pop(key, None)
