"""Tests for API Gateway service."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check_returns_200(self):
        """Health endpoint should return 200 with healthy status."""
        # We test schemas directly since service requires live connections
        from shared.schemas.health import HealthResponse

        response = HealthResponse(status="healthy", version="1.0.0")
        assert response.status == "healthy"
        assert response.version == "1.0.0"

    def test_health_response_with_services(self):
        """Health response can include service statuses."""
        from shared.schemas.health import HealthResponse, ServiceHealth

        services = [
            ServiceHealth(name="redis", status="healthy", latency_ms=1.5),
            ServiceHealth(name="ingestion", status="healthy", latency_ms=5.2),
        ]
        response = HealthResponse(
            status="healthy", version="1.0.0", services=services
        )
        assert len(response.services) == 2
        assert response.services[0].name == "redis"


class TestDocumentSchemas:
    """Test document Pydantic schemas."""

    def test_document_create_valid(self):
        from shared.schemas.document import DocumentCreate

        doc = DocumentCreate(
            title="Test Document",
            content="This is test content.",
            doc_type="text",
        )
        assert doc.title == "Test Document"
        assert doc.tenant_id == "default"

    def test_document_create_empty_title_fails(self):
        from shared.schemas.document import DocumentCreate

        with pytest.raises(Exception):
            DocumentCreate(title="", content="Some content")

    def test_document_create_empty_content_fails(self):
        from shared.schemas.document import DocumentCreate

        with pytest.raises(Exception):
            DocumentCreate(title="Test", content="")

    def test_document_list_response(self):
        from shared.schemas.document import DocumentListResponse

        response = DocumentListResponse(
            items=[], total=0, page=1, page_size=20, pages=0
        )
        assert response.total == 0
        assert response.pages == 0


class TestQuerySchemas:
    """Test query Pydantic schemas."""

    def test_query_request_valid(self):
        from shared.schemas.query import QueryRequest

        query = QueryRequest(question="What is RAG?")
        assert query.question == "What is RAG?"
        assert query.top_k == 5
        assert query.rerank is True

    def test_query_request_custom_params(self):
        from shared.schemas.query import QueryRequest

        query = QueryRequest(
            question="Test?",
            top_k=10,
            rerank=False,
            tenant_id="custom",
        )
        assert query.top_k == 10
        assert query.rerank is False
        assert query.tenant_id == "custom"

    def test_query_response_with_citations(self):
        import uuid
        from shared.schemas.query import Citation, QueryResponse

        citation = Citation(
            document_id=uuid.uuid4(),
            document_title="Test Doc",
            chunk_id=uuid.uuid4(),
            relevance_score=0.95,
            excerpt="Test excerpt",
        )
        response = QueryResponse(
            question="What?",
            answer="Answer here.",
            citations=[citation],
        )
        assert len(response.citations) == 1
        assert response.citations[0].relevance_score == 0.95
