"""Integration tests for Retrieval service — query analysis, SQL safety, and reranking."""

from unittest.mock import AsyncMock

import pytest


class TestQueryAnalysis:
    """Test query analysis node."""

    @pytest.mark.asyncio
    async def test_analyze_query_extracts_keywords(self):
        from services.retrieval.app.graphs.nodes import analyze_query_node

        state = {"question": "What are the benefits of retrieval augmented generation?"}
        result = await analyze_query_node(state)

        analysis = result["query_analysis"]
        assert analysis["original_query"] == state["question"]
        assert len(analysis["keywords"]) > 0
        # Words <= 3 chars should be excluded
        assert "the" not in analysis["keywords"]
        assert "are" not in analysis["keywords"]

    @pytest.mark.asyncio
    async def test_analyze_empty_query(self):
        from services.retrieval.app.graphs.nodes import analyze_query_node

        state = {"question": ""}
        result = await analyze_query_node(state)
        assert result["query_analysis"]["keywords"] == []


class TestSQLInjectionPrevention:
    """Verify that keyword search is safe from SQL injection."""

    def test_keyword_search_uses_parameterized_queries(self):
        """Ensure the keyword search code does NOT use f-string interpolation for SQL."""
        import inspect

        from services.retrieval.app.graphs.nodes import retrieve_node

        source = inspect.getsource(retrieve_node)
        # Must NOT contain direct string interpolation in SQL
        assert "f\"c.content ILIKE '%{" not in source
        # Must use parameterized placeholders
        assert ":kw_" in source


class TestGenerateNode:
    """Test answer generation node."""

    @pytest.mark.asyncio
    async def test_generate_with_no_chunks_returns_fallback(self):
        from services.retrieval.app.graphs.nodes import generate_node

        state = {
            "reranked_chunks": [],
            "retrieved_chunks": [],
            "question": "What is RAG?",
            "http_client": AsyncMock(),
        }
        result = await generate_node(state)
        assert "couldn't find" in result["answer"].lower()
        assert result["model"] == "none"


class TestCiteNode:
    """Test citation extraction node."""

    @pytest.mark.asyncio
    async def test_cite_extracts_top_citations(self):
        from services.retrieval.app.graphs.nodes import cite_node

        chunks = [
            {
                "document_id": "doc-1",
                "document_title": "Test Doc",
                "chunk_id": "chunk-1",
                "content": "Some relevant content about RAG systems.",
            },
            {
                "document_id": "doc-2",
                "document_title": "Test Doc 2",
                "chunk_id": "chunk-2",
                "content": "Another piece of information.",
            },
        ]
        state = {
            "answer": "RAG systems use [Source 1] for retrieval.",
            "reranked_chunks": chunks,
        }
        result = await cite_node(state)
        assert len(result["citations"]) >= 1
        assert result["citations"][0]["document_id"] == "doc-1"
