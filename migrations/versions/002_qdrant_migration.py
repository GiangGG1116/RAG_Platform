"""002 - Remove pgvector embedding, add Qdrant point reference.

Revision ID: 002_qdrant_migration
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "002_qdrant_migration"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add qdrant_point_id column to chunks
    op.add_column(
        "chunks",
        sa.Column("qdrant_point_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("idx_chunks_qdrant_point_id", "chunks", ["qdrant_point_id"])

    # Drop pgvector HNSW index and embedding column
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw")
    op.drop_column("chunks", "embedding")


def downgrade() -> None:
    # Re-create pgvector extension and embedding column
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "chunks",
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
    )
    op.execute("""
        CREATE INDEX idx_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """)

    # Drop qdrant column
    op.drop_index("idx_chunks_qdrant_point_id")
    op.drop_column("chunks", "qdrant_point_id")
