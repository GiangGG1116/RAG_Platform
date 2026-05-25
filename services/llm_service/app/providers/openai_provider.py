"""OpenAI LLM provider with retry and rate limiting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from shared.config import get_settings

from app.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1.0


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider with exponential backoff retry."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {self._settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate text using OpenAI Chat Completions API."""
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": self._settings.openai_model,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant that answers questions based on provided context. Always cite sources when available."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "text": data["choices"][0]["message"]["content"],
                    "model": data["model"],
                    "usage": data.get("usage", {}),
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    logger.warning("Rate limited, retrying in %.1fs", delay)
                    await asyncio.sleep(delay)
                    continue
                raise
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise

        return {"text": "Generation failed after retries.", "model": "error", "usage": {}}

    async def embed(self, text: str) -> dict[str, Any]:
        """Generate embeddings using OpenAI Embeddings API."""
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.post(
                    "/embeddings",
                    json={
                        "model": self._settings.openai_embedding_model,
                        "input": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embedding = data["data"][0]["embedding"]

                return {
                    "embedding": embedding,
                    "model": data["model"],
                    "dimension": len(embedding),
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                    continue
                raise
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise

        raise RuntimeError("Embedding generation failed after retries")

    async def rerank(
        self, query: str, passages: list[str]
    ) -> dict[str, Any]:
        """Rerank using LLM-based scoring.

        Uses the chat model to score relevance since OpenAI
        doesn't have a dedicated reranking endpoint.
        """
        scores: list[float] = []

        for passage in passages:
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json={
                        "model": self._settings.openai_model,
                        "messages": [
                            {"role": "system", "content": "Rate the relevance of the passage to the query on a scale of 0 to 1. Only respond with a number."},
                            {"role": "user", "content": f"Query: {query}\n\nPassage: {passage[:500]}"},
                        ],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"].strip()
                score = float(text)
                scores.append(min(max(score, 0), 1))
            except (ValueError, Exception):
                scores.append(0.5)  # Default score

        return {"scores": scores, "model": self._settings.openai_model}
