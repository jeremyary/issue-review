# This project was developed with assistance from AI tools.
"""Content indexing and sync utilities."""

from indexer.sync import (
    sync_catalog,
    check_catalog_freshness,
    ensure_catalog_fresh,
    clone_or_pull_repo,
    sync_content,
    fetch_published_quickstarts,
    REPOS_DIR,
)
from indexer.content import (
    ContentChunk,
    extract_all_chunks,
    extract_readme_chunks,
    extract_helm_chunks,
    extract_notebook_chunks,
    extract_dependency_chunks,
    compute_content_hash,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    split_markdown_by_headers,
    split_yaml_by_sections,
)
from indexer.embeddings import (
    generate_embedding,
    generate_embeddings_batch,
    store_chunks,
    semantic_search,
    update_sync_metadata,
    get_sync_metadata,
    delete_quickstart_chunks,
)
from indexer.coverage import (
    sync_coverage,
    get_coverage_freshness,
    detect_features_in_content,
    scan_quickstart_for_features,
)

__all__ = [
    # Sync
    "sync_catalog",
    "check_catalog_freshness",
    "ensure_catalog_fresh",
    "clone_or_pull_repo",
    "sync_content",
    "fetch_published_quickstarts",
    "REPOS_DIR",
    # Content extraction
    "ContentChunk",
    "extract_all_chunks",
    "extract_readme_chunks",
    "extract_helm_chunks",
    "extract_notebook_chunks",
    "extract_dependency_chunks",
    "compute_content_hash",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "split_markdown_by_headers",
    "split_yaml_by_sections",
    # Embeddings & search
    "generate_embedding",
    "generate_embeddings_batch",
    "store_chunks",
    "semantic_search",
    "update_sync_metadata",
    "get_sync_metadata",
    "delete_quickstart_chunks",
    # Coverage detection
    "sync_coverage",
    "get_coverage_freshness",
    "detect_features_in_content",
    "scan_quickstart_for_features",
]


def index_quickstart(quickstart_id: str, repo_name: str, repo_path: str, quiet: bool = False) -> int:
    """Index content from a quickstart repository.
    
    This is the main entry point for indexing a single quickstart:
    1. Extract README and Helm chart content
    2. Generate embeddings
    3. Store in pgvector database
    
    Args:
        quickstart_id: ID from catalog.yaml
        repo_name: GitHub repo name
        repo_path: Path to cloned repository
        quiet: Suppress output
    
    Returns:
        Number of chunks indexed
    """
    from rich.console import Console
    console = Console()
    
    if not quiet:
        console.print(f"  Indexing {quickstart_id}...")
    
    # Extract content
    chunks = extract_all_chunks(repo_path, quickstart_id, repo_name)
    
    if not chunks:
        if not quiet:
            console.print(f"    [dim]No content found to index[/dim]")
        return 0
    
    if not quiet:
        console.print(f"    Extracted {len(chunks)} chunks")
    
    # Generate embeddings
    texts = [chunk.content for chunk in chunks]
    embeddings = generate_embeddings_batch(texts)
    
    # Store in database
    stored = store_chunks(chunks, embeddings)
    
    # Update metadata
    readme_content = ""
    for chunk in chunks:
        if chunk.content_type == "readme":
            readme_content += chunk.content
    
    readme_hash = compute_content_hash(readme_content) if readme_content else None
    update_sync_metadata(quickstart_id, readme_hash=readme_hash, chunk_count=stored)
    
    if not quiet:
        console.print(f"    [green]Stored {stored} chunks[/green]")
    
    return stored
