"""Common utilities for the RAG platform."""

import hashlib
import time
import uuid
from typing import Any


def generate_id() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


def hash_content(content: str) -> str:
    """Generate a SHA-256 hash of content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def timer() -> float:
    """Return current time in seconds for measuring latency."""
    return time.perf_counter()


def calculate_latency_ms(start: float) -> float:
    """Calculate latency in milliseconds from a start time."""
    return round((time.perf_counter() - start) * 1000, 2)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def build_cache_key(*parts: str) -> str:
    """Build a namespaced cache key."""
    return ":".join(parts)


def chunk_list(lst: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of specified size."""
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]
