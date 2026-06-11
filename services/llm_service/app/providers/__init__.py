"""
LLM providers package.

Supports OpenAI and local model providers with a common interface.
"""

from __future__ import annotations

from app.providers.base import BaseLLMProvider
from app.providers.local_provider import LocalProvider
from app.providers.openai_provider import OpenAIProvider
from shared.config import get_settings


def get_llm_provider() -> BaseLLMProvider:
    """Factory: return the configured LLM provider."""
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    return LocalProvider()


__all__ = ["BaseLLMProvider", "OpenAIProvider", "LocalProvider", "get_llm_provider"]
