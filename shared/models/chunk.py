"""Chunk SQLAlchemy model with pgvector embedding support."""
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.config import get_settings
from shared.models.base import Base


class Chunk(Base):
    """Represents a text chunk with its vector embedding."""

    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dimension),
        nullable=True,
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_document_index", "document_id", "chunk_index", unique=True),
        Index(
            "idx_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, doc_id={self.document_id}, index={self.chunk_index})>"
