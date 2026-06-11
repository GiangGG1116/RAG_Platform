"""
LangGraph node implementations for the RAG pipeline.

Each node performs one step: query analysis, retrieval, reranking,
generation, and citation extraction.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text

from shared.cache import get_cache
from shared.config import get_settings
from shared.database import get_db_session
from shared.utils import build_cache_key

logger = logging.getLogger(__name__)


async def analyze_query_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze the user query to extract intent and keywords."""
    question = state["question"]

    # Simple keyword extraction (in production, use LLM for this)
    keywords = [word.lower().strip(".,!?;:") for word in question.split() if len(word) > 3]

    analysis = {
        "original_query": question,
        "keywords": keywords,
        "intent": "search",  # Could be: search, compare, summarize, explain
        "language": "en",
    }

    logger.info("Query analyzed: %d keywords extracted", len(keywords))
    return {"query_analysis": analysis}


def _build_filter_clauses(
    filters: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Build additional SQL WHERE clauses and params from retrieval filters.

    Returns a tuple of (sql_fragment, params_dict).  The sql_fragment
    contains zero or more ``AND …`` clauses that can be appended directly
    after the base ``WHERE`` clause in the retrieval queries.
    """
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    # ── Filter by specific document IDs ─────────────────────────
    document_ids = filters.get("document_ids")
    if document_ids:
        placeholders = ", ".join([f":filter_doc_id_{i}" for i in range(len(document_ids))])
        clauses.append(f"d.id IN ({placeholders})")
        for i, doc_id in enumerate(document_ids):
            params[f"filter_doc_id_{i}"] = doc_id

    # ── Filter by document type ─────────────────────────────────
    doc_types = filters.get("doc_types")
    if doc_types:
        placeholders = ", ".join([f":filter_doc_type_{i}" for i in range(len(doc_types))])
        clauses.append(f"d.doc_type IN ({placeholders})")
        for i, dt in enumerate(doc_types):
            params[f"filter_doc_type_{i}"] = dt

    # ── Filter by creation date range ───────────────────────────
    date_from = filters.get("date_from")
    if date_from:
        clauses.append("d.created_at >= :filter_date_from")
        params["filter_date_from"] = date_from

    date_to = filters.get("date_to")
    if date_to:
        clauses.append("d.created_at <= :filter_date_to")
        params["filter_date_to"] = date_to

    # ── Filter by JSONB metadata on documents ───────────────────
    metadata_filters = filters.get("metadata_filters")
    if metadata_filters and isinstance(metadata_filters, dict):
        for idx, (key, value) in enumerate(metadata_filters.items()):
            param_name = f"filter_meta_{idx}"
            # Use the @> (contains) operator for exact key/value match
            clauses.append(f"d.metadata @> CAST(:{param_name} AS jsonb)")
            params[param_name] = json.dumps({key: value})

    sql_fragment = ""
    if clauses:
        sql_fragment = " AND " + " AND ".join(clauses)

    return sql_fragment, params


async def retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    """Hybrid retrieval: vector similarity + keyword search with optional filters."""
    question = state["question"]
    tenant_id = state["tenant_id"]
    top_k = state["top_k"]
    filters = state.get("filters")

    # Check cache first (include filters in the cache key for correctness)
    cache = await get_cache()
    filters_fingerprint = json.dumps(filters, sort_keys=True, default=str) if filters else ""
    cache_key = build_cache_key("rag", "retrieve", tenant_id, question[:100], filters_fingerprint)
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Cache hit for retrieval query")
        return {"retrieved_chunks": cached}

    settings = get_settings()
    retrieved_chunks: list[dict] = []

    # Build advanced filter SQL clauses
    filter_sql, filter_params = _build_filter_clauses(filters)
    if filter_sql:
        logger.info("Applying retrieval filters: %s", list(filter_params.keys()))

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
            vector_query = text(f"""
                SELECT c.id, c.document_id, c.content, c.chunk_index, c.metadata,
                       d.title as document_title,
                       1 - (c.embedding <=> CAST(:embedding AS vector)) as similarity_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.tenant_id = :tenant_id
                  AND c.embedding IS NOT NULL
                  {filter_sql}
                ORDER BY c.embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            """)  # noqa: S608
            params = {"embedding": embedding_str, "tenant_id": tenant_id, "top_k": top_k, **filter_params}
            result = await session.execute(vector_query, params)
            for row in result.mappings():
                retrieved_chunks.append(
                    {
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "document_title": row["document_title"],
                        "content": row["content"],
                        "score": float(row["similarity_score"]),
                        "metadata": row["metadata"] or {},
                    }
                )
        else:
            # Fallback: keyword search with ILIKE (parameterized to prevent SQL injection)
            keywords = state.get("query_analysis", {}).get("keywords", [])
            if keywords:
                safe_keywords = keywords[:5]
                keyword_conditions = " OR ".join([f"c.content ILIKE :kw_{i}" for i in range(len(safe_keywords))])
                keyword_query = text(f"""
                    SELECT c.id, c.document_id, c.content, c.chunk_index, c.metadata,
                           d.title as document_title,
                           0.5 as similarity_score
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.tenant_id = :tenant_id
                      AND ({keyword_conditions})
                      {filter_sql}
                    LIMIT :top_k
                """)  # noqa: S608
                params = {"tenant_id": tenant_id, "top_k": top_k, **filter_params}
                for i, kw in enumerate(safe_keywords):
                    params[f"kw_{i}"] = f"%{kw}%"
                result = await session.execute(keyword_query, params)
                for row in result.mappings():
                    retrieved_chunks.append(
                        {
                            "chunk_id": str(row["id"]),
                            "document_id": str(row["document_id"]),
                            "document_title": row["document_title"],
                            "content": row["content"],
                            "score": float(row["similarity_score"]),
                            "metadata": row["metadata"] or {},
                        }
                    )

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
        context_parts.append(f"[Source {i + 1}: {chunk['document_title']}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    # Call LLM service
    prompt = f"""Based on the following context, answer the question accurately.
Always cite your sources using [Source N] format.
If the context doesn't contain enough information, say so.
Answer in the same language as the user's question.

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
            citations.append(
                {
                    "document_id": chunk["document_id"],
                    "document_title": chunk["document_title"],
                    "chunk_id": chunk["chunk_id"],
                    "relevance_score": max(relevance, 0.1),
                    "excerpt": chunk["content"][:200],
                }
            )

    logger.info("Extracted %d citations", len(citations))
    return {"citations": citations}


# ── Streaming Node (used outside the compiled graph) ────────────


def build_rag_prompt(question: str, chunks: list[dict]) -> str:
    """Build the RAG prompt from question and context chunks."""
    if not chunks:
        return question

    context_parts = []
    for i, chunk in enumerate(chunks[:5]):
        context_parts.append(f"[Source {i + 1}: {chunk['document_title']}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    return f"""Based on the following context, answer the question accurately.
Always cite your sources using [Source N] format.
If the context doesn't contain enough information, say so.
Answer in the same language as the user's question.

Context:
{context}

Question: {question}

Answer:"""


async def generate_stream_node(
    question: str,
    chunks: list[dict],
    http_client: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Stream LLM generation token-by-token via the LLM service SSE endpoint.

    Yields dicts:
      - {"token": "partial text"}
      - {"done": True, "model": ..., "usage": ...}
    """
    settings = get_settings()

    if not chunks:
        yield {"token": "I couldn't find relevant information to answer your question."}
        yield {"done": True, "model": "none", "usage": {}}
        return

    prompt = build_rag_prompt(question, chunks)

    try:
        async with http_client.stream(
            "POST",
            f"{settings.llm_service_url}/api/v1/generate/stream",
            json={"prompt": prompt, "max_tokens": 1024, "temperature": 0.1},
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: ") :]
                try:
                    chunk = json.loads(payload)
                    yield chunk
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        logger.exception("Streaming generation via LLM service failed")
        yield {"token": "Sorry, I encountered an error generating the answer. Please try again."}
        yield {"error": str(e), "done": True, "model": "error", "usage": {}}
