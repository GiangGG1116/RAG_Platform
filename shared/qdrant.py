"""
Async Qdrant client for vector storage and similarity search.

Provides a singleton client, collection management, and CRUD operations
for vector points used by the RAG pipeline.
"""

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from shared.config import get_settings

logger = logging.getLogger(__name__)

# ── Singleton client ─────────────────────────────────────────────

_client: AsyncQdrantClient | None = None


async def get_qdrant_client() -> AsyncQdrantClient:
    """Return a cached async Qdrant client (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=30,
        )
        logger.info("Qdrant client connected to %s", settings.qdrant_url)
    return _client


async def close_client() -> None:
    """Close the Qdrant client. Call during app shutdown."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("Qdrant client closed")


# ── Collection management ────────────────────────────────────────


async def ensure_collection() -> None:
    """Create the chunks collection if it does not exist.

    Uses cosine distance and HNSW index (Qdrant default) with
    parameters aligned to the former pgvector HNSW config.
    """
    settings = get_settings()
    client = await get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]

    if collection_name not in existing:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimension,
                distance=models.Distance.COSINE,
                hnsw_config=models.HnswConfigDiff(m=16, ef_construct=200),
            ),
        )
        # Create payload indexes for filtered search
        for field in ("tenant_id", "document_id"):
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="doc_type",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="created_at",
            field_schema=models.PayloadSchemaType.DATETIME,
        )
        logger.info(
            "Created Qdrant collection '%s' (dim=%d, cosine)",
            collection_name,
            settings.embedding_dimension,
        )
    else:
        logger.info("Qdrant collection '%s' already exists", collection_name)


# ── Vector CRUD ──────────────────────────────────────────────────


async def upsert_vectors(
    points: list[models.PointStruct],
) -> None:
    """Upsert a batch of points into the chunks collection."""
    settings = get_settings()
    client = await get_qdrant_client()
    await client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=points,
    )
    logger.debug("Upserted %d points to Qdrant", len(points))


def _build_qdrant_filter(
    tenant_id: str,
    filters: dict[str, Any] | None = None,
) -> models.Filter:
    """Convert the platform's filter dict into a Qdrant Filter.

    Supports: document_ids, doc_types, date_from, date_to, metadata_filters.
    """
    must: list[models.Condition] = [
        models.FieldCondition(
            key="tenant_id",
            match=models.MatchValue(value=tenant_id),
        ),
    ]

    if not filters:
        return models.Filter(must=must)

    # Filter by specific document IDs
    document_ids = filters.get("document_ids")
    if document_ids:
        must.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchAny(any=[str(d) for d in document_ids]),
            )
        )

    # Filter by document type
    doc_types = filters.get("doc_types")
    if doc_types:
        must.append(
            models.FieldCondition(
                key="doc_type",
                match=models.MatchAny(any=list(doc_types)),
            )
        )

    # Filter by creation date range
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from or date_to:
        must.append(
            models.FieldCondition(
                key="created_at",
                range=models.DatetimeRange(
                    gte=str(date_from) if date_from else None,
                    lte=str(date_to) if date_to else None,
                ),
            )
        )

    # Filter by metadata key/value pairs (nested payload)
    metadata_filters = filters.get("metadata_filters")
    if metadata_filters and isinstance(metadata_filters, dict):
        for key, value in metadata_filters.items():
            must.append(
                models.FieldCondition(
                    key=f"metadata.{key}",
                    match=models.MatchValue(value=value),
                )
            )

    return models.Filter(must=must)


async def search_vectors(
    query_vector: list[float],
    tenant_id: str,
    limit: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[models.ScoredPoint]:
    """Search for similar vectors with tenant and optional filters.

    Returns ScoredPoint objects whose `.payload` contains the full
    chunk content so no additional DB query is needed.
    """
    settings = get_settings()
    client = await get_qdrant_client()

    qdrant_filter = _build_qdrant_filter(tenant_id, filters)

    results = await client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=query_vector,
        query_filter=qdrant_filter,
        limit=limit,
        with_payload=True,
    )

    logger.debug(
        "Qdrant search returned %d results (tenant=%s)",
        len(results.points),
        tenant_id,
    )
    return results.points


async def delete_vectors_by_document(document_id: str) -> None:
    """Delete all vectors belonging to a specific document."""
    settings = get_settings()
    client = await get_qdrant_client()

    await client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    ),
                ]
            )
        ),
    )
    logger.info("Deleted Qdrant vectors for document %s", document_id)
