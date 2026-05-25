"""Tests for Retrieval service."""

from __future__ import annotations

import pytest


class TestRAGSchemas:
    """Test RAG-related schemas."""

    def test_retrieved_chunk(self):
        import uuid
        from shared.schemas.query import RetrievedChunk

        chunk = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Test Doc",
            content="Test content",
            score=0.85,
        )
        assert chunk.score == 0.85
        assert chunk.content == "Test content"

    def test_query_request_bounds(self):
        from shared.schemas.query import QueryRequest

        # top_k within bounds
        q = QueryRequest(question="Test?", top_k=50)
        assert q.top_k == 50

        # top_k out of bounds
        with pytest.raises(Exception):
            QueryRequest(question="Test?", top_k=100)

    def test_query_request_min_length(self):
        from shared.schemas.query import QueryRequest

        with pytest.raises(Exception):
            QueryRequest(question="")
