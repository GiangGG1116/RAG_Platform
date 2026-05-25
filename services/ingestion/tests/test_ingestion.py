"""Tests for Ingestion service."""

from __future__ import annotations

import pytest


class TestIngestionGraphNodes:
    """Test ingestion pipeline node logic."""

    def test_split_into_sentences(self):
        """Test sentence splitting utility."""
        from services.ingestion.app.graphs.nodes import _split_into_sentences

        text = "Hello world. How are you? I am fine!"
        sentences = _split_into_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "Hello world."

    def test_split_empty_text(self):
        from services.ingestion.app.graphs.nodes import _split_into_sentences

        sentences = _split_into_sentences("")
        assert len(sentences) == 0

    def test_split_single_sentence(self):
        from services.ingestion.app.graphs.nodes import _split_into_sentences

        sentences = _split_into_sentences("Just one sentence.")
        assert len(sentences) == 1


class TestSharedUtils:
    """Test shared utility functions."""

    def test_hash_content(self):
        from shared.utils import hash_content

        h1 = hash_content("hello")
        h2 = hash_content("hello")
        h3 = hash_content("world")
        assert h1 == h2
        assert h1 != h3

    def test_truncate_text(self):
        from shared.utils import truncate_text

        assert truncate_text("short", 10) == "short"
        assert truncate_text("a" * 300, 200).endswith("...")
        assert len(truncate_text("a" * 300, 200)) == 203

    def test_build_cache_key(self):
        from shared.utils import build_cache_key

        key = build_cache_key("rag", "retrieve", "tenant1")
        assert key == "rag:retrieve:tenant1"

    def test_chunk_list(self):
        from shared.utils import chunk_list

        result = chunk_list([1, 2, 3, 4, 5], 2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_generate_id(self):
        from shared.utils import generate_id

        id1 = generate_id()
        id2 = generate_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID format


class TestConfig:
    """Test configuration module."""

    def test_settings_defaults(self):
        from shared.config import Settings

        settings = Settings()
        assert settings.postgres_host == "postgres"
        assert settings.redis_port == 6379
        assert settings.chunk_size == 512

    def test_database_url_property(self):
        from shared.config import Settings

        settings = Settings()
        url = settings.database_url
        assert "postgresql+asyncpg://" in url
        assert "rag_platform" in url

    def test_api_keys_list(self):
        from shared.config import Settings

        settings = Settings(api_keys="key1,key2,key3")
        assert settings.api_keys_list == ["key1", "key2", "key3"]

    def test_redis_url_property(self):
        from shared.config import Settings

        settings = Settings(redis_host="localhost", redis_port=6379, redis_db=0)
        assert settings.redis_url == "redis://localhost:6379/0"
