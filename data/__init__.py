# This project was developed with assistance from AI tools.
"""Data loaders for catalog, features, and coverage files."""

import os
from datetime import datetime
from typing import Optional

import yaml

# Data directory path
DATA_DIR = os.path.dirname(__file__)

# File paths
CATALOG_FILE = os.path.join(DATA_DIR, "catalog.yaml")
FEATURES_FILE = os.path.join(DATA_DIR, "features.yaml")
COVERAGE_FILE = os.path.join(DATA_DIR, "coverage.yaml")
PERSONAS_FILE = os.path.join(DATA_DIR, "personas.yaml")


def load_yaml(filepath: str) -> dict:
    """Load a YAML file and return its contents."""
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r") as f:
        return yaml.safe_load(f) or {}


def save_yaml(filepath: str, data: dict) -> None:
    """Save data to a YAML file."""
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_catalog() -> dict:
    """Load the quickstart catalog.
    
    Returns:
        Dict with 'metadata' and 'quickstarts' keys
    """
    return load_yaml(CATALOG_FILE)


def get_published_quickstarts() -> list[dict]:
    """Get the list of published quickstarts.
    
    Returns:
        List of quickstart dicts with name, repo, description, etc.
    """
    catalog = load_catalog()
    return catalog.get("quickstarts", [])


def get_catalog_last_synced() -> Optional[datetime]:
    """Get the last sync timestamp from the catalog.
    
    Returns:
        datetime if available, None otherwise
    """
    catalog = load_catalog()
    metadata = catalog.get("metadata", {})
    last_synced = metadata.get("last_synced")
    
    if last_synced is None:
        return None
    
    if isinstance(last_synced, datetime):
        return last_synced
    
    # Parse ISO format string
    try:
        return datetime.fromisoformat(str(last_synced))
    except (ValueError, TypeError):
        return None


def update_catalog_sync_time() -> None:
    """Update the last_synced timestamp in the catalog."""
    catalog = load_catalog()
    if "metadata" not in catalog:
        catalog["metadata"] = {}
    catalog["metadata"]["last_synced"] = datetime.now().isoformat()
    save_yaml(CATALOG_FILE, catalog)


def load_features() -> list[dict]:
    """Load the OpenShift AI features catalog.
    
    Returns:
        List of feature dicts with id, name, category, description, keywords
    """
    data = load_yaml(FEATURES_FILE)
    return data.get("features", [])


def load_coverage() -> dict[str, list[str]]:
    """Load the feature coverage matrix.
    
    Returns:
        Dict mapping quickstart ID -> list of feature IDs
    """
    data = load_yaml(COVERAGE_FILE)
    coverage = data.get("coverage", {})
    
    # Normalize to {quickstart_id: [feature_ids]}
    result = {}
    for qs_id, info in coverage.items():
        if isinstance(info, dict):
            result[qs_id] = info.get("features", [])
        elif isinstance(info, list):
            result[qs_id] = info
        else:
            result[qs_id] = []
    
    return result


def load_personas() -> list[dict]:
    """Load persona definitions.
    
    Returns:
        List of persona dicts with id, name, examples, system_prompt
    """
    data = load_yaml(PERSONAS_FILE)
    return data.get("personas", [])


def get_all_demonstrated_features() -> set[str]:
    """Get set of all features demonstrated across existing quickstarts.
    
    Returns:
        Set of feature IDs that have been used in at least one quickstart
    """
    coverage = load_coverage()
    demonstrated = set()
    for features in coverage.values():
        demonstrated.update(features)
    return demonstrated
