"""Tests for LLM service."""

import pytest


class TestLocalProvider:
    """Test local/mock LLM provider."""

    @pytest.mark.asyncio
    async def test_generate(self):
        from services.llm_service.app.providers.local_provider import LocalProvider

        provider = LocalProvider()
        result = await provider.generate(prompt="What is RAG?")
        assert "text" in result
        assert result["model"] == "local-mock"
        assert len(result["text"]) > 0

    @pytest.mark.asyncio
    async def test_embed(self):
        from services.llm_service.app.providers.local_provider import LocalProvider

        provider = LocalProvider()
        result = await provider.embed(text="Hello world")
        assert "embedding" in result
        assert result["dimension"] == 1536
        assert len(result["embedding"]) == 1536

    @pytest.mark.asyncio
    async def test_embed_deterministic(self):
        from services.llm_service.app.providers.local_provider import LocalProvider

        provider = LocalProvider()
        r1 = await provider.embed(text="Hello")
        r2 = await provider.embed(text="Hello")
        assert r1["embedding"] == r2["embedding"]

    @pytest.mark.asyncio
    async def test_rerank(self):
        from services.llm_service.app.providers.local_provider import LocalProvider

        provider = LocalProvider()
        result = await provider.rerank(
            query="What is RAG?",
            passages=["RAG is retrieval augmented generation", "Pizza recipe"],
        )
        assert len(result["scores"]) == 2
        assert result["scores"][0] > result["scores"][1]  # RAG passage should score higher
