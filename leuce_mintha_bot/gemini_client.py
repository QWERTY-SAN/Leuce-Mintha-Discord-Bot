import asyncio
import logging
import random
from collections.abc import Sequence

from google import genai
from google.genai import types

from .config import MAX_INPUT_CHARS, REQUEST_TIMEOUT
from .memory import MessageTurn
from .persona import build_persona

logger = logging.getLogger("leuce_mintha.gemini")


class GeminiError(RuntimeError):
    """Safe wrapper around Gemini API failures."""


class GeminiService:
    def __init__(self, api_key: str, model: str, max_output_tokens: int, thinking_level: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level

    @staticmethod
    def _trim_message(text: str) -> str:
        text = text.strip()
        if len(text) <= MAX_INPUT_CHARS:
            return text
        return text[: MAX_INPUT_CHARS - 80].rstrip() + "\n\n[Message truncated.]"

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
                parts=[types.Part.from_text(text=cls._trim_message(user_message))],
            )
        )
        return contents

    async def generate(self, history: Sequence[MessageTurn], user_message: str, mode: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=build_persona(mode),
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
                raise GeminiError("Gemini returned an empty response.")
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning("Gemini timeout on attempt %d/3.", attempt + 1)
            except Exception as exc:
                if not self._retryable(exc):
                    raise GeminiError("Gemini rejected the request.") from exc
                last_error = exc
                logger.warning("Retryable Gemini failure on attempt %d/3: %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep((2 ** attempt) + random.uniform(0.1, 0.6))
        raise GeminiError("Gemini request failed after retries.") from last_error

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code in {408, 429, 500, 502, 503, 504}:
            return True
        text = f"{type(exc).__name__} {exc}".lower()
        return any(term in text for term in (
            "timeout", "timed out", "deadline", "rate limit",
            "resource exhausted", "temporarily unavailable", "service unavailable",
        ))

    async def close(self) -> None:
        try:
            await self.client.aio.aclose()
        finally:
            self.client.close()
