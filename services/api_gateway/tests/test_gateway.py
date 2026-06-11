"""Integration tests for API Gateway — auth, rate limiting, and proxying."""

from datetime import UTC

import pytest

from shared.auth import UserRole, create_access_token, verify_token


class TestJWTAuth:
    """Test JWT token creation and verification."""

    def test_create_token_returns_valid_token(self):
        token_resp = create_access_token(
            subject="testuser",
            role=UserRole.EDITOR,
            tenant_id="company-a",
        )
        assert token_resp.access_token
        assert token_resp.token_type == "bearer"  # noqa: S105
        assert token_resp.role == "editor"
        assert token_resp.expires_in > 0

    def test_verify_valid_token(self):
        token_resp = create_access_token(subject="testuser", role=UserRole.ADMIN)
        data = verify_token(token_resp.access_token)
        assert data.sub == "testuser"
        assert data.role == UserRole.ADMIN

    def test_verify_expired_token_raises(self):
        from datetime import datetime, timedelta

        import jwt as pyjwt

        from shared.config import get_settings

        settings = get_settings()
        payload = {
            "sub": "expired_user",
            "role": "viewer",
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=2),
        }
        token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(ValueError, match="expired"):
            verify_token(token)

    def test_verify_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token("totally.invalid.token")

    def test_create_token_for_each_role(self):
        for role in UserRole:
            token_resp = create_access_token(subject=f"user_{role.value}", role=role)
            data = verify_token(token_resp.access_token)
            assert data.role == role


class TestRBAC:
    """Test role-based access control permission checks."""

    def test_admin_can_access_everything(self):
        from shared.auth import check_permission

        assert check_permission(UserRole.ADMIN, "POST", "/api/v1/documents") is True
        assert check_permission(UserRole.ADMIN, "DELETE", "/api/v1/documents/123") is True
        assert check_permission(UserRole.ADMIN, "POST", "/api/v1/admin/tokens") is True
        assert check_permission(UserRole.ADMIN, "POST", "/api/v1/query") is True

    def test_editor_can_write_documents(self):
        from shared.auth import check_permission

        assert check_permission(UserRole.EDITOR, "POST", "/api/v1/documents") is True
        assert check_permission(UserRole.EDITOR, "DELETE", "/api/v1/documents/123") is True
        assert check_permission(UserRole.EDITOR, "POST", "/api/v1/query") is True

    def test_editor_cannot_create_tokens(self):
        from shared.auth import check_permission

        assert check_permission(UserRole.EDITOR, "POST", "/api/v1/admin/tokens") is False

    def test_viewer_can_only_read(self):
        from shared.auth import check_permission

        assert check_permission(UserRole.VIEWER, "POST", "/api/v1/query") is True
        assert check_permission(UserRole.VIEWER, "GET", "/api/v1/documents") is True

    def test_viewer_cannot_write_documents(self):
        from shared.auth import check_permission

        assert check_permission(UserRole.VIEWER, "POST", "/api/v1/documents") is False
        assert check_permission(UserRole.VIEWER, "DELETE", "/api/v1/documents/123") is False


class TestHealthSchemas:
    """Test health check schemas."""

    def test_health_response(self):
        from shared.schemas.health import HealthResponse

        response = HealthResponse(status="healthy", version="1.0.0")
        assert response.status == "healthy"
        assert response.version == "1.0.0"


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
        from pydantic import ValidationError

        from shared.schemas.document import DocumentCreate

        with pytest.raises(ValidationError):
            DocumentCreate(title="", content="Some content")


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

        query = QueryRequest(question="Test?", top_k=10, rerank=False, tenant_id="custom")
        assert query.top_k == 10
        assert query.rerank is False
