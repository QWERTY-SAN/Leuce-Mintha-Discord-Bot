import asyncio
import logging
import random
from collections.abc import Sequence

from google import genai
from google.genai import types

from .config import MAX_INPUT_CHARS, REQUEST_TIMEOUT
from .memory import MessageTurn
from .persona import BOT_PERSONA

logger = logging.getLogger("leuce_mintha.gemini")


class GeminiError(RuntimeError):
    """Safe wrapper for Gemini request failures."""


class GeminiService:
    def __init__(self, api_key: str, model: str, max_output_tokens: int, thinking_level: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level

    @staticmethod
    def _normalize_user_message(text: str) -> str:
        text = text.strip()
        if len(text) <= MAX_INPUT_CHARS:
            return text
        cutoff = max(0, MAX_INPUT_CHARS - 80)
        return text[:cutoff].rstrip() + "\n\n[Message truncated to keep the conversation manageable.]"

    @classmethod
    def build_contents(cls, history: Sequence[MessageTurn], user_message: str) -> list[types.Content]:
        contents: list[types.Content] = []
        for turn in history:
            contents.append(
                types.Content(
                    role=turn.role,
                    parts=[types.Part.from_text(text=turn.text)],
                )
            )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=cls._normalize_user_message(user_message))],
            )
        )
        return contents

    async def generate(self, history: Sequence[MessageTurn], user_message: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=BOT_PERSONA,
            max_output_tokens=self.max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
        )
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model,
                        contents=self.build_contents(history, user_message),
                        config=config,
                    ),
                    timeout=REQUEST_TIMEOUT,
                )
                text = getattr(response, "text", None)
                if text:
                    return text.strip()
                raise GeminiError("Gemini returned no text.")
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning("Gemini request timed out on attempt %d/3.", attempt + 1)
            except Exception as exc:
                if not self._retryable(exc):
                    raise GeminiError(f"Gemini request rejected: {exc}") from exc
                last_error = exc
                logger.warning("Retryable Gemini failure on attempt %d/3: %s", attempt + 1, exc)

            if attempt < 2:
                await asyncio.sleep((2**attempt) + random.uniform(0.1, 0.5))

        raise GeminiError("Gemini request failed after retries.") from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code in {408, 429, 500, 502, 503, 504}:
            return True
        text = f"{type(exc).__name__} {exc}".lower()
        return any(
            term in text
            for term in (
                "timeout",
                "timed out",
                "deadline",
                "rate limit",
                "resource exhausted",
                "temporarily unavailable",
                "service unavailable",
            )
        )

    async def close(self) -> None:
        await self.client.aio.aclose()
        self.client.close()
