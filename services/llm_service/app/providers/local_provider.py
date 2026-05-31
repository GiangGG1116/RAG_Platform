"""Local/mock LLM provider for development and testing."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, AsyncIterator

from app.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_MOCK_ANSWER = (
    "Based on the provided context, here is the answer: "
    "The system processes documents through an ingestion pipeline, "
    "chunks them into smaller pieces, generates embeddings, "
    "and stores them for retrieval. When a query is made, "
    "it performs hybrid search combining vector similarity and "
    "keyword matching, then generates a response using the "
    "most relevant chunks. [Source 1] [Source 2]"
)


class LocalProvider(BaseLLMProvider):
    """Mock LLM provider for local development.

    Returns deterministic responses for testing.
    Replace with actual local model integration (e.g., Ollama, vLLM).
    """

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Return a mock response based on the prompt."""
        return {
            "text": _MOCK_ANSWER,
            "model": "local-mock",
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(_MOCK_ANSWER.split())},
        }

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> AsyncIterator[dict[str, Any]]:
        """Simulate token-by-token streaming with small delays."""
        words = _MOCK_ANSWER.split()
        for i, word in enumerate(words):
            token = word if i == 0 else f" {word}"
            yield {"token": token}
            await asyncio.sleep(0.03)  # ~30ms per token to simulate LLM

        yield {
            "done": True,
            "model": "local-mock",
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(words)},
        }

    async def embed(self, text: str) -> dict[str, Any]:
        """Return a mock embedding vector."""
        # Generate deterministic pseudo-random embedding based on text hash
        random.seed(hash(text) % (2**32))
        dimension = 1536
        embedding = [random.gauss(0, 0.1) for _ in range(dimension)]

        return {
            "embedding": embedding,
            "model": "local-mock",
            "dimension": dimension,
        }

    async def rerank(
        self, query: str, passages: list[str]
    ) -> dict[str, Any]:
        """Return mock reranking scores based on keyword overlap."""
        query_words = set(query.lower().split())
        scores: list[float] = []

        for passage in passages:
            passage_words = set(passage.lower().split())
            overlap = len(query_words & passage_words)
            score = min(overlap / max(len(query_words), 1), 1.0)
            scores.append(round(score, 3))

        return {"scores": scores, "model": "local-mock"}
