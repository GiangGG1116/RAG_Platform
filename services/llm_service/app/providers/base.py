"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class BaseLLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Generate text from a prompt.

        Args:
            prompt: The user prompt text.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            messages: Optional pre-built message list (overrides prompt).
                      Each dict must have ``role`` and ``content`` keys.

        Returns:
            dict with keys: text, model, usage
        """
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream text generation token-by-token.

        Args:
            prompt: The user prompt text.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            messages: Optional pre-built message list (overrides prompt).

        Yields:
            dicts with either:
              - {"token": "partial text"}     for each token
              - {"done": True, "model": ..., "usage": ...}  as the final chunk
        """
        ...
        # pragma: no cover — abstract, must yield to be AsyncIterator
        yield  # noqa: unreachable

    @abstractmethod
    async def embed(self, text: str) -> dict[str, Any]:
        """Generate embeddings for text.

        Returns:
            dict with keys: embedding, model, dimension
        """
        ...

    @abstractmethod
    async def rerank(
        self, query: str, passages: list[str]
    ) -> dict[str, Any]:
        """Rerank passages against a query.

        Returns:
            dict with keys: scores, model
        """
        ...
