"""001 - Initial schema: documents and chunks with pgvector.

Revision ID: 001_initial
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # Documents table
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("source", sa.String(1000), nullable=True),
        sa.Column("doc_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("tenant_id", sa.String(100), nullable=False, server_default="default", index=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_documents_tenant_status", "documents", ["tenant_id", "status"])

    # Chunks table with pgvector
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )

    # HNSW index for vector search
    op.execute("""
        CREATE INDEX idx_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """)

    # Trigram index for keyword search
    op.execute("""
        CREATE INDEX idx_chunks_content_trgm ON chunks
        USING gin (content gin_trgm_ops)
    """)

    # Auto-update trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """)
    op.execute("""
        CREATE TRIGGER update_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("""
        CREATE TRIGGER update_chunks_updated_at
        BEFORE UPDATE ON chunks
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column CASCADE")
