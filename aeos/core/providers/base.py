"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    messages: list[Message]
    model: str
    temperature: float = 0.2
    # 2048 is a safe default for local models with 4096-token context windows.
    # Cloud models (Anthropic, OpenAI) accept much larger values -- set max_tokens
    # in config.yaml or via /route commands to increase for bigger models.
    max_tokens: int = 2048
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: Any = None


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    name: str = "base"

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a completion request and return the response."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is reachable and configured."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
