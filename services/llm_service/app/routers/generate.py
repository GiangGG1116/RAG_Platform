"""LLM generation, embedding, and reranking endpoints."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
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


async def _stream_generate(provider: Any, prompt: str, max_tokens: int, temperature: float) -> AsyncIterator[str]:
    """SSE generator that yields token events from the LLM provider."""
    try:
        async for chunk in provider.generate_stream(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
    except Exception as e:
        logger.exception("Streaming generation failed")
        yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"


@router.post("/generate/stream", summary="Stream text generation (SSE)")
async def generate_text_stream(payload: GenerateRequest, request: Request) -> StreamingResponse:
    """Stream text generation token-by-token using Server-Sent Events.

    Each SSE event contains a JSON payload:
      - ``{"token": "..."}`` for each generated token
      - ``{"done": true, "model": "...", "usage": {...}}`` as the final event
    """
    provider = request.app.state.llm_provider
    return StreamingResponse(
        _stream_generate(provider, payload.prompt, payload.max_tokens, payload.temperature),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
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
