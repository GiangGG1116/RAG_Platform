"""LLM generation, embedding, and reranking endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    temperature: float = Field(default=0.1, ge=0, le=2)


class GenerateResponse(BaseModel):
    text: str
    model: str
    usage: dict = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    text: str = Field(..., min_length=1)


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model: str
    dimension: int


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    passages: list[str] = Field(..., min_length=1)


class RerankResponse(BaseModel):
    scores: list[float]
    model: str


@router.post("/generate", response_model=GenerateResponse, summary="Generate text")
async def generate_text(payload: GenerateRequest, request: Request) -> Any:
    """Generate text using the configured LLM provider."""
    provider = request.app.state.llm_provider

    try:
        result = await provider.generate(
            prompt=payload.prompt,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
        return GenerateResponse(**result)
    except Exception:
        logger.exception("LLM generation failed")
        return GenerateResponse(
            text="Error: LLM generation failed.",
            model="error",
            usage={},
        )


@router.post("/embeddings", response_model=EmbeddingResponse, summary="Generate embeddings")
async def generate_embedding(payload: EmbeddingRequest, request: Request) -> Any:
    """Generate text embeddings."""
    provider = request.app.state.llm_provider

    try:
        result = await provider.embed(text=payload.text)
        return EmbeddingResponse(**result)
    except Exception:
        logger.exception("Embedding generation failed")
        raise


@router.post("/rerank", response_model=RerankResponse, summary="Rerank passages")
async def rerank_passages(payload: RerankRequest, request: Request) -> Any:
    """Rerank passages against a query."""
    provider = request.app.state.llm_provider

    try:
        result = await provider.rerank(
            query=payload.query,
            passages=payload.passages,
        )
        return RerankResponse(**result)
    except Exception:
        logger.exception("Reranking failed")
        # Fallback: return uniform scores
        return RerankResponse(
            scores=[0.5] * len(payload.passages),
            model="fallback",
        )
