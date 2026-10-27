import asyncio
from collections.abc import AsyncIterator

from app.llm.base import ChatMessage, LLMProvider, StreamPart


class EchoProvider(LLMProvider):
    """Offline provider for local dev: repeats the last user message word by word."""

    name = "echo"

    def __init__(self, delay: float = 0.03) -> None:
        self.delay = delay

    async def stream(self, model: str, messages: list[ChatMessage]) -> AsyncIterator[StreamPart]:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        words = f"You said: {last}".split(" ")
        for i, word in enumerate(words):
            await asyncio.sleep(self.delay)
            yield word if i == 0 else " " + word
