# This project was developed with assistance from AI tools.
"""Embedding generation and vector storage for RAG."""

from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

from config import DATABASE_URL
from indexer.content import ContentChunk

# Embedding model - all-MiniLM-L6-v2 is fast and produces 384-dim vectors
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Lazy-loaded model
_model = None


def get_embedding_model():
    """Get or initialize the embedding model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBEDDING_MODEL)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embeddings. "
                "Install with: pip install sentence-transformers"
            )
    return _model


def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for text.
    
    Args:
        text: Text to embed
    
    Returns:
        List of floats (embedding vector)
    """
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently.
    
    Args:
        texts: List of texts to embed
    
    Returns:
        List of embedding vectors
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 10)
    return [e.tolist() for e in embeddings]


def get_db_connection():
    """Get a database connection with pgvector support."""
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def store_chunks(chunks: list[ContentChunk], embeddings: list[list[float]]) -> int:
    """Store content chunks and embeddings in the database.
    
    Args:
        chunks: List of ContentChunk objects
        embeddings: Corresponding embedding vectors
    
    Returns:
        Number of chunks stored
    """
    if not chunks:
        return 0
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Prepare data for bulk insert
        data = [
            (
                chunk.quickstart_id,
                chunk.repo_name,
                chunk.file_path,
                chunk.chunk_index,
                chunk.content,
                chunk.content_type,
                chunk.heading,
                emb,
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        
        # Upsert chunks
        execute_values(
            cur,
            """
            INSERT INTO content_chunks 
                (quickstart_id, repo_name, file_path, chunk_index, content, 
                 content_type, heading, embedding)
            VALUES %s
            ON CONFLICT (quickstart_id, file_path, chunk_index)
            DO UPDATE SET
                content = EXCLUDED.content,
                content_type = EXCLUDED.content_type,
                heading = EXCLUDED.heading,
                embedding = EXCLUDED.embedding,
                updated_at = CURRENT_TIMESTAMP
            """,
            data,
            template="(%s, %s, %s, %s, %s, %s, %s, %s::vector)",
        )
        
        conn.commit()
        return len(chunks)
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def update_sync_metadata(
    quickstart_id: str,
    commit_sha: str | None = None,
    readme_hash: str | None = None,
    chunk_count: int = 0,
) -> None:
    """Update sync metadata for a quickstart.
    
    Args:
        quickstart_id: Quickstart ID
        commit_sha: Git commit SHA
        readme_hash: Hash of README content
        chunk_count: Number of chunks indexed
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            INSERT INTO sync_metadata (quickstart_id, last_indexed_at, last_commit_sha, readme_hash, chunk_count)
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s)
            ON CONFLICT (quickstart_id)
            DO UPDATE SET
                last_indexed_at = CURRENT_TIMESTAMP,
                last_commit_sha = COALESCE(EXCLUDED.last_commit_sha, sync_metadata.last_commit_sha),
                readme_hash = COALESCE(EXCLUDED.readme_hash, sync_metadata.readme_hash),
                chunk_count = EXCLUDED.chunk_count
            """,
            (quickstart_id, commit_sha, readme_hash, chunk_count),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_sync_metadata(quickstart_id: str) -> Optional[dict]:
    """Get sync metadata for a quickstart.
    
    Args:
        quickstart_id: Quickstart ID
    
    Returns:
        Dict with metadata or None if not found
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            SELECT last_indexed_at, last_commit_sha, readme_hash, chunk_count
            FROM sync_metadata
            WHERE quickstart_id = %s
            """,
            (quickstart_id,),
        )
        row = cur.fetchone()
        
        if row:
            return {
                "last_indexed_at": row[0],
                "last_commit_sha": row[1],
                "readme_hash": row[2],
                "chunk_count": row[3],
            }
        return None
    finally:
        cur.close()
        conn.close()


def semantic_search(
    query: str,
    limit: int = 10,
    quickstart_ids: list[str] | None = None,
    content_types: list[str] | None = None,
) -> list[dict]:
    """Perform semantic search over indexed content.
    
    Args:
        query: Search query
        limit: Maximum number of results
        quickstart_ids: Filter by quickstart IDs
        content_types: Filter by content types
    
    Returns:
        List of matching chunks with similarity scores
    """
    # Generate query embedding
    query_embedding = generate_embedding(query)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Build query with optional filters
        sql = """
            SELECT 
                quickstart_id, repo_name, file_path, chunk_index,
                content, content_type, heading,
                1 - (embedding <=> %s::vector) as similarity
            FROM content_chunks
            WHERE 1=1
        """
        params = [query_embedding]
        
        if quickstart_ids:
            sql += " AND quickstart_id = ANY(%s)"
            params.append(quickstart_ids)
        
        if content_types:
            sql += " AND content_type = ANY(%s)"
            params.append(content_types)
        
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_embedding, limit])
        
        cur.execute(sql, params)
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "quickstart_id": row[0],
                "repo_name": row[1],
                "file_path": row[2],
                "chunk_index": row[3],
                "content": row[4],
                "content_type": row[5],
                "heading": row[6],
                "similarity": float(row[7]),
            })
        
        return results
        
    finally:
        cur.close()
        conn.close()


def delete_quickstart_chunks(quickstart_id: str) -> int:
    """Delete all chunks for a quickstart.
    
    Args:
        quickstart_id: Quickstart ID
    
    Returns:
        Number of chunks deleted
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "DELETE FROM content_chunks WHERE quickstart_id = %s",
            (quickstart_id,),
        )
        deleted = cur.rowcount
        
        cur.execute(
            "DELETE FROM sync_metadata WHERE quickstart_id = %s",
            (quickstart_id,),
        )
        
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()
