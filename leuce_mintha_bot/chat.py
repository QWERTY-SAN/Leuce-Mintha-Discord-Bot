import asyncio
import weakref

from .config import MAX_CONCURRENT_REQUESTS, MAX_QUEUE_WAIT
from .gemini_client import GeminiError, GeminiService
from .memory import ConversationMemory


class LeuceMinthaChat:
    def __init__(self, gemini: GeminiService, memory: ConversationMemory) -> None:
        self.gemini = gemini
        self.memory = memory
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._active_requests = 0
        self._total_requests = 0

    def _get_lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    @property
    def active_requests(self) -> int:
        return self._active_requests

    @property
    def total_requests(self) -> int:
        return self._total_requests

    async def ask(self, key: str, message: str) -> str:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=MAX_QUEUE_WAIT)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("The response queue is currently full.") from exc

        try:
            async with self._get_lock(key):
                self._active_requests += 1
                self._total_requests += 1
                try:
                    history = list(self.memory.get(key))
                    reply = await self.gemini.generate(history, message)
                    self.memory.add_turn(key, "user", message)
                    self.memory.add_turn(key, "model", reply)
                    return reply
                except GeminiError:
                    raise
                finally:
                    self._active_requests -= 1
        finally:
            self._semaphore.release()

    def reset(self, key: str) -> None:
        self.memory.clear(key)

    def prune_memory(self) -> int:
        return self.memory.prune()
