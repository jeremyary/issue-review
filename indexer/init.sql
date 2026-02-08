-- Initialize pgvector extension and tables for RAG content indexing

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Content chunks table
-- Stores extracted content from quickstart repositories
CREATE TABLE IF NOT EXISTS content_chunks (
    id SERIAL PRIMARY KEY,
    quickstart_id VARCHAR(100) NOT NULL,  -- matches catalog.yaml id
    repo_name VARCHAR(100) NOT NULL,       -- GitHub repo name
    file_path TEXT NOT NULL,               -- path within repo (e.g., "README.md")
    chunk_index INTEGER NOT NULL,          -- order within file
    content TEXT NOT NULL,                 -- raw text content
    content_type VARCHAR(50) NOT NULL,     -- "readme", "helm_values", "helm_chart"
    heading TEXT,                          -- section heading with hierarchy (e.g., "Section > Subsection")
    embedding vector(384),                 -- embedding vector (all-MiniLM-L6-v2 = 384 dims)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE (quickstart_id, file_path, chunk_index)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_chunks_quickstart ON content_chunks(quickstart_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_type ON content_chunks(content_type);
CREATE INDEX IF NOT EXISTS idx_chunks_repo ON content_chunks(repo_name);

-- Vector similarity search index (IVFFlat for moderate dataset sizes)
-- Using cosine distance for normalized embeddings
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON content_chunks 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Sync metadata table
-- Tracks when content was last indexed
CREATE TABLE IF NOT EXISTS sync_metadata (
    quickstart_id VARCHAR(100) PRIMARY KEY,
    last_indexed_at TIMESTAMP,
    last_commit_sha VARCHAR(40),
    readme_hash VARCHAR(64),
    chunk_count INTEGER DEFAULT 0
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS content_chunks_updated_at ON content_chunks;
CREATE TRIGGER content_chunks_updated_at
    BEFORE UPDATE ON content_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Grant permissions (if running as superuser)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO issue_review;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO issue_review;
