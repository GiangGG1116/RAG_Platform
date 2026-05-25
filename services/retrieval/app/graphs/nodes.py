"""
LangGraph node implementations for the RAG pipeline.

Each node performs one step: query analysis, retrieval, reranking,
generation, and citation extraction.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select, text

from shared.cache import get_cache
from shared.config import get_settings
from shared.database import get_db_session
from shared.models.chunk import Chunk
from shared.models.document import Document
from shared.utils import build_cache_key

logger = logging.getLogger(__name__)


async def analyze_query_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze the user query to extract intent and keywords."""
    question = state["question"]

    # Simple keyword extraction (in production, use LLM for this)
    keywords = [
        word.lower().strip(".,!?;:")
        for word in question.split()
        if len(word) > 3
    ]

    analysis = {
        "original_query": question,
        "keywords": keywords,
        "intent": "search",  # Could be: search, compare, summarize, explain
        "language": "en",
    }

    logger.info("Query analyzed: %d keywords extracted", len(keywords))
    return {"query_analysis": analysis}


async def retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    """Hybrid retrieval: vector similarity + keyword search."""
    question = state["question"]
    tenant_id = state["tenant_id"]
    top_k = state["top_k"]

    # Check cache first
    cache = await get_cache()
    cache_key = build_cache_key("rag", "retrieve", tenant_id, question[:100])
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Cache hit for retrieval query")
        return {"retrieved_chunks": cached}

    settings = get_settings()
    retrieved_chunks: list[dict] = []

    # Get query embedding from LLM service
    http_client = state["http_client"]
    try:
        embed_response = await http_client.post(
            f"{settings.llm_service_url}/api/v1/embeddings",
            json={"text": question},
        )
        embed_response.raise_for_status()
        query_embedding = embed_response.json().get("embedding", [])
    except Exception:
        logger.warning("Failed to get query embedding, falling back to keyword search")
        query_embedding = None

    async with get_db_session() as session:
        if query_embedding:
            # Vector similarity search using pgvector
            embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"
            vector_query = text("""
                SELECT c.id, c.document_id, c.content, c.chunk_index, c.metadata,
                       d.title as document_title,
                       1 - (c.embedding <=> :embedding::vector) as similarity_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.tenant_id = :tenant_id
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> :embedding::vector
                LIMIT :top_k
            """)
            result = await session.execute(
                vector_query,
                {"embedding": embedding_str, "tenant_id": tenant_id, "top_k": top_k},
            )
            for row in result.mappings():
                retrieved_chunks.append({
                    "chunk_id": str(row["id"]),
                    "document_id": str(row["document_id"]),
                    "document_title": row["document_title"],
                    "content": row["content"],
                    "score": float(row["similarity_score"]),
                    "metadata": row["metadata"] or {},
                })
        else:
            # Fallback: keyword search with ILIKE
            keywords = state.get("query_analysis", {}).get("keywords", [])
            if keywords:
                keyword_conditions = " OR ".join(
                    [f"c.content ILIKE '%{kw}%'" for kw in keywords[:5]]
                )
                keyword_query = text(f"""
                    SELECT c.id, c.document_id, c.content, c.chunk_index, c.metadata,
                           d.title as document_title,
                           0.5 as similarity_score
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.tenant_id = :tenant_id
                      AND ({keyword_conditions})
                    LIMIT :top_k
                """)
                result = await session.execute(
                    keyword_query,
                    {"tenant_id": tenant_id, "top_k": top_k},
                )
                for row in result.mappings():
                    retrieved_chunks.append({
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "document_title": row["document_title"],
                        "content": row["content"],
                        "score": float(row["similarity_score"]),
                        "metadata": row["metadata"] or {},
                    })

    # Cache results
    if retrieved_chunks:
        await cache.set(cache_key, retrieved_chunks, ttl_seconds=300)

    logger.info("Retrieved %d chunks for query", len(retrieved_chunks))
    return {"retrieved_chunks": retrieved_chunks}


async def rerank_node(state: dict[str, Any]) -> dict[str, Any]:
    """Rerank retrieved chunks using cross-encoder scoring via LLM service."""
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return {"reranked_chunks": []}

    question = state["question"]
    http_client = state["http_client"]
    settings = get_settings()

    try:
        response = await http_client.post(
            f"{settings.llm_service_url}/api/v1/rerank",
            json={
                "query": question,
                "passages": [chunk["content"] for chunk in chunks],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        scores = response.json().get("scores", [])

        # Re-sort by reranking scores
        for i, chunk in enumerate(chunks):
            if i < len(scores):
                chunk["score"] = scores[i]

        reranked = sorted(chunks, key=lambda c: c["score"], reverse=True)
        logger.info("Reranked %d chunks", len(reranked))
        return {"reranked_chunks": reranked}

    except Exception:
        logger.warning("Reranking failed, using original ranking")
        return {"reranked_chunks": chunks}


async def generate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate answer using LLM with retrieved context."""
    chunks = state.get("reranked_chunks") or state.get("retrieved_chunks", [])
    question = state["question"]
    http_client = state["http_client"]
    settings = get_settings()

    if not chunks:
        return {
            "answer": "I couldn't find relevant information to answer your question.",
            "model": "none",
        }

    # Build context from chunks
    context_parts = []
    for i, chunk in enumerate(chunks[:5]):
        context_parts.append(
            f"[Source {i + 1}: {chunk['document_title']}]\n{chunk['content']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # Call LLM service
    prompt = f"""Based on the following context, answer the question accurately.
Always cite your sources using [Source N] format.
If the context doesn't contain enough information, say so.

Context:
{context}

Question: {question}

Answer:"""

    try:
        response = await http_client.post(
            f"{settings.llm_service_url}/api/v1/generate",
            json={
                "prompt": prompt,
                "max_tokens": 1024,
                "temperature": 0.1,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
        answer = result.get("text", "")
        model = result.get("model", "unknown")

        logger.info("LLM generated answer (%d chars) using model %s", len(answer), model)
        return {"answer": answer, "model": model}

    except Exception:
        logger.exception("LLM generation failed")
        return {
            "answer": "Sorry, I encountered an error generating the answer. Please try again.",
            "model": "error",
        }


async def cite_node(state: dict[str, Any]) -> dict[str, Any]:
    """Extract and verify citations from the generated answer."""
    answer = state.get("answer", "")
    chunks = state.get("reranked_chunks") or state.get("retrieved_chunks", [])

    citations = []
    for i, chunk in enumerate(chunks[:5]):
        # Check if the source is referenced in the answer
        source_ref = f"[Source {i + 1}]"
        relevance = 0.9 - (i * 0.1)  # Higher relevance for top-ranked

        if source_ref in answer or i < 3:  # Always cite top 3
            citations.append({
                "document_id": chunk["document_id"],
                "document_title": chunk["document_title"],
                "chunk_id": chunk["chunk_id"],
                "relevance_score": max(relevance, 0.1),
                "excerpt": chunk["content"][:200],
            })

    logger.info("Extracted %d citations", len(citations))
    return {"citations": citations}
