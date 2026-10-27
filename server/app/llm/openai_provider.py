from collections.abc import AsyncIterator
from typing import Any

import openai

from app.llm.base import ChatMessage, LLMProvider, ProviderError, StreamPart, Usage

# errors where waiting and trying again has a real chance of working
RETRYABLE = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        timeout: float,
        base_url: str | None = None,
        http_client: Any = None,  # injectable so tests never hit the network
        name: str = "openai",
    ) -> None:
        self.name = name
        # retries are handled by the gateway, so turn off the sdk's own retry loop
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            http_client=http_client,
        )

    async def stream(self, model: str, messages: list[ChatMessage]) -> AsyncIterator[StreamPart]:
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                stream=True,
                # the final chunk then carries token counts for the whole request
                stream_options={"include_usage": True},
            )
            async for chunk in response:
                if chunk.usage is not None:
                    yield Usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except RETRYABLE as err:
            raise ProviderError(f"openai: {err}", retryable=True) from err
        except openai.OpenAIError as err:
            raise ProviderError(f"openai: {err}", retryable=False) from err
