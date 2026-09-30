import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import TypeAlias

ConversationKey: TypeAlias = tuple[int, int]


@dataclass(slots=True)
class MessageTurn:
    role: str
    text: str


@dataclass(slots=True)
class Conversation:
    turns: deque[MessageTurn]
    touched_at: float


class ConversationMemory:
    def __init__(self, max_messages: int, ttl_seconds: int, max_conversations: int) -> None:
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds
        self.max_conversations = max_conversations
        self._data: OrderedDict[ConversationKey, Conversation] = OrderedDict()

    def _expired(self, conversation: Conversation, now: float) -> bool:
        return now - conversation.touched_at >= self.ttl_seconds

    def prune(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        removed = 0
        expired = [
            key for key, conversation in self._data.items()
            if self._expired(conversation, now)
        ]
        for key in expired:
            if self._data.pop(key, None) is not None:
                removed += 1
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)
            removed += 1
        return removed

    def get(self, key: ConversationKey) -> list[MessageTurn]:
        now = time.monotonic()
        self.prune(now)
        conversation = self._data.get(key)
        if conversation is None or self._expired(conversation, now):
            conversation = Conversation(deque(maxlen=self.max_messages), now)
            self._data[key] = conversation
        else:
            conversation.touched_at = now
            self._data.move_to_end(key)
        return list(conversation.turns)

    def add_turn(self, key: ConversationKey, role: str, text: str) -> None:
        self.get(key)
        conversation = self._data[key]
        conversation.turns.append(MessageTurn(role=role, text=text))
        conversation.touched_at = time.monotonic()
        self._data.move_to_end(key)
        self.prune()

    def clear(self, key: ConversationKey) -> None:
        self._data.pop(key, None)

    def message_count(self, key: ConversationKey) -> int:
        return len(self.get(key))

    def conversation_count(self) -> int:
        self.prune()
        return len(self._data)
