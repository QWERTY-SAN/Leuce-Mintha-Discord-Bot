import asyncio
import logging
from collections.abc import Sequence

from google import genai
from google.genai import types

log = logging.getLogger("leuce_mintha.gemini")


class GeminiService:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_output_tokens: int,
        request_timeout: int,
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.request_timeout = request_timeout

    async def generate(
        self,
        user_text: str,
        history: Sequence[tuple[str, str]],
        persona: str,
    ) -> str:
        contents: list[types.Content] = []

        for role, text in history:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=text)],
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)],
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=persona,
            max_output_tokens=self.max_output_tokens,
        )

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self.request_timeout,
                )

                text = getattr(response, "text", None)
                if text:
                    return text
                raise RuntimeError("Gemini returned an empty response.")

            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    break

                delay = 2 ** attempt
                log.warning(
                    "Gemini request failed on attempt %d/3; retrying in %ds: %s",
                    attempt + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        raise RuntimeError("Gemini request failed after retries.") from last_error
