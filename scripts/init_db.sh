#!/bin/bash
# Initialize PostgreSQL with pgvector extension
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable pgvector extension
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;

    -- Create documents table
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title VARCHAR(500) NOT NULL,
        content TEXT,
        source VARCHAR(1000),
        doc_type VARCHAR(50) NOT NULL DEFAULT 'text',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        metadata JSONB NOT NULL DEFAULT '{}',
        tenant_id VARCHAR(100) NOT NULL DEFAULT 'default',
        chunk_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Create chunks table with pgvector
    CREATE TABLE IF NOT EXISTS chunks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        embedding vector(1536),
        token_count INTEGER NOT NULL DEFAULT 0,
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(document_id, chunk_index)
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_documents_tenant_status ON documents(tenant_id, status);
    CREATE INDEX IF NOT EXISTS idx_documents_title ON documents(title);
    CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);

    -- HNSW index for vector similarity search
    CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);

    -- Trigram index for keyword search
    CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm ON chunks
        USING gin (content gin_trgm_ops);

    -- Updated_at trigger
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS \$\$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    \$\$ language 'plpgsql';

    CREATE OR REPLACE TRIGGER update_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    CREATE OR REPLACE TRIGGER update_chunks_updated_at
        BEFORE UPDATE ON chunks
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

EOSQL

echo "Database initialized with pgvector extension and tables."
