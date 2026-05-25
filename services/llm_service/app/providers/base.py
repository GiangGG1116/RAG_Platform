"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate text from a prompt.

        Returns:
            dict with keys: text, model, usage
        """
        ...

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
