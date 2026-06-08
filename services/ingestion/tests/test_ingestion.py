"""Integration tests for Ingestion service — validation, chunking, and dedup."""

from unittest.mock import AsyncMock, patch

import pytest


class TestIngestionValidation:
    """Test document validation logic."""

    @pytest.mark.asyncio
    async def test_validate_empty_content_fails(self):
        from services.ingestion.app.graphs.nodes import validate_document_node

        state = {"content": "", "document_id": "test-id"}
        with patch("services.ingestion.app.graphs.nodes.get_cache", new_callable=AsyncMock):
            result = await validate_document_node(state)
            assert result["is_valid"] is False
            assert "empty" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_oversized_content_fails(self):
        from services.ingestion.app.graphs.nodes import MAX_CONTENT_LENGTH, validate_document_node

        state = {"content": "x" * (MAX_CONTENT_LENGTH + 1), "document_id": "test-id"}
        with patch("services.ingestion.app.graphs.nodes.get_cache", new_callable=AsyncMock) as mock_cache:
            mock_cache_inst = AsyncMock()
            mock_cache_inst.get = AsyncMock(return_value=None)
            mock_cache_inst.set = AsyncMock(return_value=True)
            mock_cache.return_value = mock_cache_inst
            result = await validate_document_node(state)
            assert result["is_valid"] is False
            assert "max length" in result["error"]


class TestTextChunking:
    """Test text chunking logic."""

    @pytest.mark.asyncio
    async def test_chunk_empty_text_returns_empty(self):
        from services.ingestion.app.graphs.nodes import chunk_text_node

        state = {"extracted_text": "", "document_id": "test-id", "title": "Test"}
        result = await chunk_text_node(state)
        assert result["chunks"] == []
        assert result["chunk_count"] == 0

    @pytest.mark.asyncio
    async def test_chunk_short_text_single_chunk(self):
        from services.ingestion.app.graphs.nodes import chunk_text_node

        state = {
            "extracted_text": "This is a short text.",
            "document_id": "test-id",
            "title": "Test",
        }
        result = await chunk_text_node(state)
        assert result["chunk_count"] == 1
        assert result["chunks"][0]["content"] == "This is a short text."

    @pytest.mark.asyncio
    async def test_chunk_long_text_multiple_chunks(self):
        from services.ingestion.app.graphs.nodes import chunk_text_node

        # Generate text larger than default chunk_size (512)
        sentences = [f"Sentence number {i} with some content. " for i in range(100)]
        state = {
            "extracted_text": " ".join(sentences),
            "document_id": "test-id",
            "title": "Test",
        }
        result = await chunk_text_node(state)
        assert result["chunk_count"] > 1
        for chunk in result["chunks"]:
            assert chunk["content"]
            assert chunk["chunk_index"] >= 0
            assert chunk["token_count"] > 0


class TestIngestionSchemas:
    """Test ingestion-related schemas."""

    def test_supported_doc_types(self):
        from services.ingestion.app.graphs.nodes import SUPPORTED_TYPES

        assert "text" in SUPPORTED_TYPES
        assert "pdf" in SUPPORTED_TYPES
        assert "md" in SUPPORTED_TYPES
