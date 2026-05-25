"""Seed script to populate the database with sample documents."""

from __future__ import annotations

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import get_db_session
from shared.models.document import Document, DocumentStatus


SAMPLE_DOCUMENTS = [
    {
        "title": "Introduction to Retrieval Augmented Generation",
        "content": """Retrieval-Augmented Generation (RAG) is a technique that enhances Large Language Models
by retrieving relevant information from external knowledge bases before generating responses.
RAG combines the power of retrieval systems with generative models to produce more accurate,
up-to-date, and verifiable answers. The key components are: a document store for knowledge,
an embedding model for vector representations, a retrieval system for finding relevant chunks,
and a language model for generating the final answer with proper citations.""",
        "doc_type": "text",
        "metadata": {"category": "AI", "author": "System"},
    },
    {
        "title": "Microservice Architecture Best Practices",
        "content": """Microservice architecture decomposes applications into small, loosely coupled services.
Key principles include: single responsibility per service, independent deployment, decentralized
data management, API-based communication, and infrastructure automation. Benefits include
improved scalability, technology flexibility, and team autonomy. Challenges include distributed
system complexity, data consistency, and operational overhead. Use event-driven communication
with message brokers like RabbitMQ for async operations and implement circuit breakers for
resilience.""",
        "doc_type": "text",
        "metadata": {"category": "Architecture", "author": "System"},
    },
    {
        "title": "Vector Databases and Similarity Search",
        "content": """Vector databases store and index high-dimensional vectors for efficient similarity search.
pgvector is a PostgreSQL extension that adds vector similarity search capabilities. It supports
multiple index types: IVFFlat for approximate nearest neighbor search and HNSW (Hierarchical
Navigable Small World) for faster queries at higher memory cost. Cosine similarity, L2 distance,
and inner product are common distance metrics. HNSW indices provide sub-linear query time with
configurable parameters: m (connections per layer) and ef_construction (build quality).""",
        "doc_type": "text",
        "metadata": {"category": "Database", "author": "System"},
    },
]


async def seed() -> None:
    """Insert sample documents."""
    async with get_db_session() as session:
        for doc_data in SAMPLE_DOCUMENTS:
            doc = Document(
                title=doc_data["title"],
                content=doc_data["content"],
                doc_type=doc_data["doc_type"],
                metadata_=doc_data["metadata"],
                status=DocumentStatus.PENDING,
                tenant_id="default",
            )
            session.add(doc)
        print(f"Seeded {len(SAMPLE_DOCUMENTS)} sample documents.")


if __name__ == "__main__":
    asyncio.run(seed())
