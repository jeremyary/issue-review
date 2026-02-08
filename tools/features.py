# This project was developed with assistance from AI tools.
"""Tools for OpenShift AI platform feature discovery and management."""

import json
from pathlib import Path

from llm.tools import Tool
from data import load_yaml, save_yaml

# Path to features catalog
FEATURES_FILE = Path(__file__).parent.parent / "data" / "features.yaml"
COVERAGE_FILE = Path(__file__).parent.parent / "data" / "coverage.yaml"


def _load_features() -> list[dict]:
    """Load features from the catalog."""
    data = load_yaml(FEATURES_FILE)
    return data.get("features", [])


def _load_coverage() -> dict:
    """Load feature coverage data."""
    data = load_yaml(COVERAGE_FILE)
    return data or {}


def _save_coverage(coverage: dict):
    """Save feature coverage data."""
    save_yaml(COVERAGE_FILE, coverage)


def search_features(query: str) -> str:
    """Search for platform features matching a query.
    
    Args:
        query: Search query (matches against name, description, keywords)
    
    Returns:
        JSON string with matching features
    """
    features = _load_features()
    query_lower = query.lower()
    
    matches = []
    for feature in features:
        # Check name, description, category
        searchable = (
            feature.get("name", "").lower() +
            feature.get("description", "").lower() +
            feature.get("category", "").lower() +
            " ".join(feature.get("keywords", [])).lower()
        )
        
        if query_lower in searchable:
            matches.append({
                "id": feature.get("id"),
                "name": feature.get("name"),
                "category": feature.get("category"),
                "description": feature.get("description"),
            })
    
    return json.dumps({
        "query": query,
        "matches": matches,
        "count": len(matches),
    })


def get_feature(feature_id: str) -> str:
    """Get full details of a specific feature.
    
    Args:
        feature_id: The feature ID to retrieve
    
    Returns:
        JSON string with feature details
    """
    features = _load_features()
    
    for feature in features:
        if feature.get("id") == feature_id:
            return json.dumps({
                "found": True,
                "feature": feature,
            })
    
    return json.dumps({
        "found": False,
        "error": f"Feature '{feature_id}' not found",
    })


def list_features_by_category(category: str) -> str:
    """List all features in a category.
    
    Args:
        category: Category name (e.g., "Model Serving", "ML Pipelines")
    
    Returns:
        JSON string with features in the category
    """
    features = _load_features()
    category_lower = category.lower()
    
    matches = []
    for feature in features:
        if feature.get("category", "").lower() == category_lower:
            matches.append({
                "id": feature.get("id"),
                "name": feature.get("name"),
                "description": feature.get("description"),
            })
    
    # If no exact match, try partial match
    if not matches:
        for feature in features:
            if category_lower in feature.get("category", "").lower():
                matches.append({
                    "id": feature.get("id"),
                    "name": feature.get("name"),
                    "category": feature.get("category"),
                    "description": feature.get("description"),
                })
    
    return json.dumps({
        "category": category,
        "features": matches,
        "count": len(matches),
    })


def get_feature_coverage(feature_ids: list[str] | None = None) -> str:
    """Get coverage information for features (which quickstarts demonstrate them).
    
    Args:
        feature_ids: Optional list of feature IDs to check. If None, returns all coverage.
    
    Returns:
        JSON string with coverage information
    """
    coverage = _load_coverage()
    feature_coverage = coverage.get("feature_coverage", {})
    
    if feature_ids is None:
        return json.dumps({
            "coverage": feature_coverage,
            "total_features_tracked": len(feature_coverage),
        })
    
    result = {}
    for fid in feature_ids:
        if fid in feature_coverage:
            result[fid] = feature_coverage[fid]
        else:
            result[fid] = {"quickstarts": [], "count": 0}
    
    return json.dumps({
        "requested": feature_ids,
        "coverage": result,
    })


def get_all_features() -> str:
    """Get all platform features organized by category.
    
    Returns:
        JSON string with all features grouped by category
    """
    features = _load_features()
    
    by_category = {}
    for feature in features:
        category = feature.get("category", "Other")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append({
            "id": feature.get("id"),
            "name": feature.get("name"),
            "description": feature.get("description"),
        })
    
    return json.dumps({
        "categories": list(by_category.keys()),
        "features_by_category": by_category,
        "total_features": len(features),
    })


def add_feature(
    feature_id: str,
    name: str,
    category: str,
    description: str,
    keywords: list[str],
) -> str:
    """Add a new feature to the catalog.
    
    Args:
        feature_id: Unique ID for the feature
        name: Display name
        category: Category (e.g., "Model Serving")
        description: Brief description
        keywords: Keywords for matching
    
    Returns:
        JSON string with result
    """
    data = load_yaml(FEATURES_FILE)
    features = data.get("features", [])
    
    # Check if already exists
    for feature in features:
        if feature.get("id") == feature_id:
            return json.dumps({
                "success": False,
                "error": f"Feature '{feature_id}' already exists",
            })
    
    # Add new feature
    new_feature = {
        "id": feature_id,
        "name": name,
        "category": category,
        "description": description,
        "keywords": keywords,
    }
    features.append(new_feature)
    data["features"] = features
    
    save_yaml(FEATURES_FILE, data)
    
    return json.dumps({
        "success": True,
        "feature": new_feature,
    })


def update_feature_coverage(feature_id: str, quickstart_id: str) -> str:
    """Record that a quickstart demonstrates a feature.
    
    Args:
        feature_id: The feature being demonstrated
        quickstart_id: The quickstart demonstrating it
    
    Returns:
        JSON string with result
    """
    coverage = _load_coverage()
    
    if "feature_coverage" not in coverage:
        coverage["feature_coverage"] = {}
    
    if feature_id not in coverage["feature_coverage"]:
        coverage["feature_coverage"][feature_id] = {
            "quickstarts": [],
            "count": 0,
        }
    
    fc = coverage["feature_coverage"][feature_id]
    if quickstart_id not in fc["quickstarts"]:
        fc["quickstarts"].append(quickstart_id)
        fc["count"] = len(fc["quickstarts"])
    
    _save_coverage(coverage)
    
    return json.dumps({
        "success": True,
        "feature_id": feature_id,
        "quickstart_id": quickstart_id,
        "total_quickstarts": fc["count"],
    })


# Tool definitions for LLM function calling
search_features_tool = Tool(
    name="search_features",
    description="Search for OpenShift AI platform features matching a query. Use this to find features by name, description, or keywords.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to match against feature names, descriptions, and keywords",
            }
        },
        "required": ["query"],
    },
    function=search_features,
)

get_feature_tool = Tool(
    name="get_feature",
    description="Get detailed information about a specific platform feature by its ID.",
    parameters={
        "type": "object",
        "properties": {
            "feature_id": {
                "type": "string",
                "description": "The feature ID (e.g., 'kserve', 'vllm', 'rag')",
            }
        },
        "required": ["feature_id"],
    },
    function=get_feature,
)

list_features_by_category_tool = Tool(
    name="list_features_by_category",
    description="List all platform features in a specific category (e.g., 'Model Serving', 'ML Pipelines', 'Governance & Trust').",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Category name to filter by",
            }
        },
        "required": ["category"],
    },
    function=list_features_by_category,
)

get_feature_coverage_tool = Tool(
    name="get_feature_coverage",
    description="Check which quickstarts demonstrate specific features. Shows coverage data for features.",
    parameters={
        "type": "object",
        "properties": {
            "feature_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of feature IDs to check coverage for. Omit to get all coverage.",
            }
        },
        "required": [],
    },
    function=get_feature_coverage,
)

get_all_features_tool = Tool(
    name="get_all_features",
    description="Get a complete list of all OpenShift AI platform features, organized by category.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    function=get_all_features,
)

add_feature_tool = Tool(
    name="add_feature",
    description="Add a new feature to the OpenShift AI platform features catalog. Use this when you discover a platform capability that isn't tracked.",
    parameters={
        "type": "object",
        "properties": {
            "feature_id": {
                "type": "string",
                "description": "Unique ID for the feature (lowercase, underscores, e.g., 'model_mesh', 'vllm')",
            },
            "name": {
                "type": "string",
                "description": "Human-readable display name (e.g., 'ModelMesh', 'vLLM Inference')",
            },
            "category": {
                "type": "string",
                "description": "Category (e.g., 'Model Serving', 'ML Pipelines', 'Governance & Trust')",
            },
            "description": {
                "type": "string",
                "description": "Brief description of the feature",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords for matching (e.g., ['serving', 'inference', 'runtime'])",
            },
        },
        "required": ["feature_id", "name", "category", "description", "keywords"],
    },
    function=add_feature,
)

update_feature_coverage_tool = Tool(
    name="update_feature_coverage",
    description="Record that a quickstart demonstrates a specific feature. Use this to update the feature coverage matrix.",
    parameters={
        "type": "object",
        "properties": {
            "feature_id": {
                "type": "string",
                "description": "ID of the feature being demonstrated",
            },
            "quickstart_id": {
                "type": "string",
                "description": "ID of the quickstart demonstrating the feature",
            },
        },
        "required": ["feature_id", "quickstart_id"],
    },
    function=update_feature_coverage,
)

# Read-only tools (safe for all agents)
FEATURE_TOOLS_READONLY = [
    search_features_tool,
    get_feature_tool,
    list_features_by_category_tool,
    get_feature_coverage_tool,
    get_all_features_tool,
]

# All feature tools including write operations
FEATURE_TOOLS = [
    search_features_tool,
    get_feature_tool,
    list_features_by_category_tool,
    get_feature_coverage_tool,
    get_all_features_tool,
    add_feature_tool,
    update_feature_coverage_tool,
]
