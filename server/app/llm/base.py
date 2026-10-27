from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


# providers yield text pieces, and optionally one Usage with the token counts
StreamPart = str | Usage


class ProviderError(Exception):
    """Raised by providers. retryable tells the gateway if trying again could help."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def stream(self, model: str, messages: list[ChatMessage]) -> AsyncIterator[StreamPart]:
        """Yield text chunks (and Usage if the api reports it). Raise ProviderError on failure."""
