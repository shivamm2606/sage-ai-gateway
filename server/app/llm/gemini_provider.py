from collections.abc import AsyncIterator

import httpx
import httpx2
from google import genai
from google.genai import errors, types

from app.llm.base import ChatMessage, LLMProvider, ProviderError, StreamPart, Usage

RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
# the sdk can run on either httpx or its fork httpx2, so catch network errors from both
TRANSPORT_ERRORS = (httpx.TransportError, httpx2.TransportError)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, timeout: float) -> None:
        # gemini wants the timeout in milliseconds
        self.client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )

    async def stream(self, model: str, messages: list[ChatMessage]) -> AsyncIterator[StreamPart]:
        # gemini takes the system prompt separately and calls the assistant "model"
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
        config = types.GenerateContentConfig(system_instruction=system)

        try:
            response = await self.client.aio.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            usage = None
            async for chunk in response:
                # every chunk repeats the running totals, the last one is final
                if chunk.usage_metadata is not None:
                    usage = chunk.usage_metadata
                if chunk.text:
                    yield chunk.text
            if usage is not None:
                yield Usage(
                    prompt_tokens=usage.prompt_token_count or 0,
                    # thinking models bill their hidden reasoning tokens as output too
                    completion_tokens=(usage.candidates_token_count or 0)
                    + (usage.thoughts_token_count or 0),
                )
        except errors.APIError as err:
            raise ProviderError(f"gemini: {err}", retryable=err.code in RETRYABLE_CODES) from err
        except TRANSPORT_ERRORS as err:
            raise ProviderError(f"gemini: {err}", retryable=True) from err
