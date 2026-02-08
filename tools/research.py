# This project was developed with assistance from AI tools.
"""Research tools for semantic search and content retrieval."""

import json

from llm.tools import Tool


def semantic_search(query: str, limit: int = 5, quickstart_ids: list[str] | None = None) -> str:
    """Search indexed quickstart content using semantic similarity.
    
    Args:
        query: Natural language search query
        limit: Maximum number of results (default: 5)
        quickstart_ids: Optional list of quickstart IDs to filter results
    
    Returns:
        JSON string with search results
    """
    try:
        from indexer import semantic_search as _semantic_search
        
        results = _semantic_search(
            query=query,
            limit=limit,
            quickstart_ids=quickstart_ids,
        )
        
        if not results:
            return json.dumps({
                "results": [],
                "message": "No matching content found",
                "query": query,
            })
        
        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "quickstart": r["quickstart_id"],
                "file": r["file_path"],
                "heading": r.get("heading", ""),
                "content": r["content"][:500] + "..." if len(r["content"]) > 500 else r["content"],
                "similarity": round(r["similarity"], 3),
            })
        
        return json.dumps({
            "results": formatted,
            "count": len(formatted),
            "query": query,
        })
        
    except ImportError:
        return json.dumps({
            "error": "Indexer not available - database connection required",
            "results": [],
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "results": [],
        })


def get_quickstart_readme(quickstart_id: str) -> str:
    """Get the README content for a specific quickstart.
    
    Args:
        quickstart_id: ID of the quickstart
    
    Returns:
        JSON string with README content
    """
    try:
        from indexer import semantic_search as _semantic_search
        
        results = _semantic_search(
            query="README overview introduction getting started",
            limit=20,
            quickstart_ids=[quickstart_id],
            content_types=["readme"],
        )
        
        if not results:
            return json.dumps({
                "found": False,
                "error": f"No README found for quickstart '{quickstart_id}'",
            })
        
        # Reconstruct README from chunks
        chunks = sorted(results, key=lambda x: x.get("chunk_index", 0))
        content = "\n\n".join(c["content"] for c in chunks)
        
        return json.dumps({
            "found": True,
            "quickstart_id": quickstart_id,
            "content": content,
            "chunks": len(chunks),
        })
        
    except ImportError:
        return json.dumps({
            "error": "Indexer not available - database connection required",
            "found": False,
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "found": False,
        })


def get_quickstart_helm(quickstart_id: str) -> str:
    """Get Helm chart configuration for a quickstart.
    
    Args:
        quickstart_id: ID of the quickstart
    
    Returns:
        JSON string with Helm values content
    """
    try:
        from indexer import semantic_search as _semantic_search
        
        results = _semantic_search(
            query="helm values configuration deployment",
            limit=10,
            quickstart_ids=[quickstart_id],
            content_types=["helm_values", "helm_chart"],
        )
        
        if not results:
            return json.dumps({
                "found": False,
                "error": f"No Helm charts found for quickstart '{quickstart_id}'",
            })
        
        helm_files = []
        for r in results:
            helm_files.append({
                "file": r["file_path"],
                "content": r["content"],
            })
        
        return json.dumps({
            "found": True,
            "quickstart_id": quickstart_id,
            "helm_files": helm_files,
            "count": len(helm_files),
        })
        
    except ImportError:
        return json.dumps({
            "error": "Indexer not available - database connection required",
            "found": False,
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "found": False,
        })


def get_quickstart_code(quickstart_id: str, file_pattern: str = "") -> str:
    """Get code files from a quickstart.
    
    Args:
        quickstart_id: ID of the quickstart
        file_pattern: Optional pattern to filter files (e.g., ".py", "model")
    
    Returns:
        JSON string with code content
    """
    try:
        from indexer import semantic_search as _semantic_search
        
        query = f"code implementation {file_pattern}" if file_pattern else "code implementation function class"
        
        results = _semantic_search(
            query=query,
            limit=10,
            quickstart_ids=[quickstart_id],
            content_types=["code", "notebook"],
        )
        
        if not results:
            return json.dumps({
                "found": False,
                "error": f"No code files found for quickstart '{quickstart_id}'",
            })
        
        code_files = []
        for r in results:
            code_files.append({
                "file": r["file_path"],
                "content": r["content"],
                "heading": r.get("heading", ""),
            })
        
        return json.dumps({
            "found": True,
            "quickstart_id": quickstart_id,
            "code_files": code_files,
            "count": len(code_files),
        })
        
    except ImportError:
        return json.dumps({
            "error": "Indexer not available - database connection required",
            "found": False,
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "found": False,
        })


def find_similar_quickstarts(description: str, limit: int = 5) -> str:
    """Find quickstarts similar to a description.
    
    Args:
        description: Description of what you're looking for
        limit: Maximum number of results
    
    Returns:
        JSON string with similar quickstarts
    """
    try:
        from indexer import semantic_search as _semantic_search
        
        results = _semantic_search(
            query=description,
            limit=limit * 3,  # Get more to deduplicate
            content_types=["readme"],
        )
        
        if not results:
            return json.dumps({
                "results": [],
                "message": "No similar quickstarts found",
            })
        
        # Deduplicate by quickstart ID and get best match per quickstart
        seen = {}
        for r in results:
            qs_id = r["quickstart_id"]
            if qs_id not in seen or r["similarity"] > seen[qs_id]["similarity"]:
                seen[qs_id] = {
                    "quickstart_id": qs_id,
                    "similarity": round(r["similarity"], 3),
                    "summary": r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"],
                }
        
        # Sort by similarity and limit
        ranked = sorted(seen.values(), key=lambda x: x["similarity"], reverse=True)[:limit]
        
        return json.dumps({
            "results": ranked,
            "count": len(ranked),
            "description": description[:200],
        })
        
    except ImportError:
        return json.dumps({
            "error": "Indexer not available - database connection required",
            "results": [],
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "results": [],
        })


# Tool definitions for LLM function calling
semantic_search_tool = Tool(
    name="semantic_search",
    description="Search indexed quickstart content using semantic similarity. Use this to find relevant code, documentation, and examples from existing quickstarts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query describing what you're looking for",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 5, max: 10)",
                "default": 5,
            },
            "quickstart_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of quickstart IDs to search within",
            },
        },
        "required": ["query"],
    },
    function=semantic_search,
)

get_quickstart_readme_tool = Tool(
    name="get_quickstart_readme",
    description="Get the full README documentation for a specific quickstart. Use this to understand what a quickstart does and how it works.",
    parameters={
        "type": "object",
        "properties": {
            "quickstart_id": {
                "type": "string",
                "description": "ID of the quickstart to retrieve README for",
            },
        },
        "required": ["quickstart_id"],
    },
    function=get_quickstart_readme,
)

get_quickstart_helm_tool = Tool(
    name="get_quickstart_helm",
    description="Get Helm chart values and configuration for a quickstart. Use this to understand deployment configuration.",
    parameters={
        "type": "object",
        "properties": {
            "quickstart_id": {
                "type": "string",
                "description": "ID of the quickstart",
            },
        },
        "required": ["quickstart_id"],
    },
    function=get_quickstart_helm,
)

get_quickstart_code_tool = Tool(
    name="get_quickstart_code",
    description="Get code files and notebooks from a quickstart. Use this to understand implementation details.",
    parameters={
        "type": "object",
        "properties": {
            "quickstart_id": {
                "type": "string",
                "description": "ID of the quickstart",
            },
            "file_pattern": {
                "type": "string",
                "description": "Optional pattern to filter files (e.g., '.py', 'model')",
            },
        },
        "required": ["quickstart_id"],
    },
    function=get_quickstart_code,
)

find_similar_quickstarts_tool = Tool(
    name="find_similar_quickstarts",
    description="Find existing quickstarts similar to a description. Use this to check for potential overlap with new proposals.",
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Description of the quickstart concept or use case",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 5)",
                "default": 5,
            },
        },
        "required": ["description"],
    },
    function=find_similar_quickstarts,
)

# Collection of all research tools
RESEARCH_TOOLS = [
    semantic_search_tool,
    get_quickstart_readme_tool,
    get_quickstart_helm_tool,
    get_quickstart_code_tool,
    find_similar_quickstarts_tool,
]
