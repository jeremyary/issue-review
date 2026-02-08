# This project was developed with assistance from AI tools.
"""
Automatic feature coverage detection from indexed quickstart content.

Scans quickstart repositories for feature keywords and updates coverage.yaml.
"""

import os
import re
from datetime import datetime
from typing import Optional

from data import (
    load_features,
    load_yaml,
    save_yaml,
    COVERAGE_FILE,
)
from indexer.sync import REPOS_DIR


def detect_features_in_content(content: str, features: list[dict]) -> list[str]:
    """Detect which features are present in content based on keywords.
    
    Args:
        content: Text content to scan (README, code, etc.)
        features: List of feature dicts with 'id' and 'keywords'
    
    Returns:
        List of detected feature IDs
    """
    content_lower = content.lower()
    detected = []
    
    for feature in features:
        feature_id = feature.get("id", "")
        keywords = feature.get("keywords", [])
        
        # Check if any keyword appears in content
        for keyword in keywords:
            # Use word boundary matching for short keywords to avoid false positives
            if len(keyword) <= 3:
                pattern = rf'\b{re.escape(keyword.lower())}\b'
                if re.search(pattern, content_lower):
                    detected.append(feature_id)
                    break
            else:
                if keyword.lower() in content_lower:
                    detected.append(feature_id)
                    break
    
    return detected


def scan_quickstart_for_features(repo_path: str, features: list[dict]) -> list[str]:
    """Scan a quickstart repository for feature usage.
    
    Scans README, Helm values, and key source files for feature keywords.
    
    Args:
        repo_path: Path to cloned repository
        features: List of feature dicts
    
    Returns:
        List of detected feature IDs
    """
    all_content = []
    
    # Scan README files
    for readme_name in ["README.md", "readme.md", "README.rst", "README"]:
        readme_path = os.path.join(repo_path, readme_name)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                    all_content.append(f.read())
            except Exception:
                pass
            break
    
    # Scan Helm values files
    helm_paths = [
        os.path.join(repo_path, "chart", "values.yaml"),
        os.path.join(repo_path, "helm", "values.yaml"),
        os.path.join(repo_path, "values.yaml"),
    ]
    for helm_path in helm_paths:
        if os.path.exists(helm_path):
            try:
                with open(helm_path, "r", encoding="utf-8", errors="ignore") as f:
                    all_content.append(f.read())
            except Exception:
                pass
    
    # Scan Python files in common locations
    for py_dir in ["src", "app", ".", "notebooks"]:
        dir_path = os.path.join(repo_path, py_dir) if py_dir != "." else repo_path
        if os.path.isdir(dir_path):
            for root, _, files in os.walk(dir_path):
                # Skip deep directories and venv
                depth = root[len(dir_path):].count(os.sep)
                if depth > 2 or "venv" in root or "node_modules" in root:
                    continue
                    
                for fname in files:
                    if fname.endswith((".py", ".yaml", ".yml")):
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                                # Only include files with relevant size
                                if len(content) < 50000:
                                    all_content.append(content)
                        except Exception:
                            pass
    
    # Combine and detect
    combined = "\n".join(all_content)
    return detect_features_in_content(combined, features)


def sync_coverage(
    quickstart_ids: Optional[list[str]] = None,
    quiet: bool = False,
) -> dict[str, list[str]]:
    """Scan published quickstarts and update coverage.yaml with detected features.
    
    Only scans quickstarts that are listed in catalog.yaml (published quickstarts),
    not all repositories in the organization. Replaces coverage data with fresh
    results from published quickstarts only.
    
    Args:
        quickstart_ids: Optional list of quickstart IDs to scan (None = all published)
        quiet: Suppress output
    
    Returns:
        Dict of quickstart_id -> detected features
    """
    from rich.console import Console
    from data import get_published_quickstarts
    console = Console()
    
    features = load_features()
    if not features:
        if not quiet:
            console.print("[yellow]No features defined in features.yaml[/yellow]")
        return {}
    
    # Find repos to scan - only published quickstarts from catalog
    if not os.path.exists(REPOS_DIR):
        if not quiet:
            console.print("[yellow]No repos cloned. Run 'issue-review index' first.[/yellow]")
        return {}
    
    # Get published quickstarts from catalog (not all repos in directory)
    published = get_published_quickstarts()
    published_repos = {qs.get("repo") for qs in published if qs.get("repo")}
    
    # Filter to only published repos that exist locally
    available_repos = set(os.listdir(REPOS_DIR))
    repos_to_scan = published_repos & available_repos
    
    if quickstart_ids:
        repos_to_scan = {r for r in repos_to_scan if r in quickstart_ids}
    
    if not quiet:
        console.print(f"[blue]Scanning {len(repos_to_scan)} published quickstart(s) for features...[/blue]")
    
    results = {}
    
    # Build fresh coverage data (replace, don't merge)
    new_coverage = {}
    
    for repo_name in sorted(repos_to_scan):
        repo_path = os.path.join(REPOS_DIR, repo_name)
        if not os.path.isdir(repo_path):
            continue
        
        detected = scan_quickstart_for_features(repo_path, features)
        
        if detected:
            results[repo_name] = detected
            new_coverage[repo_name] = {"features": detected}
            
            if not quiet:
                console.print(f"  {repo_name}: {', '.join(detected)}")
        else:
            if not quiet:
                console.print(f"  {repo_name}: [dim]no features detected[/dim]")
    
    # Build feature_coverage summary from fresh data only
    feature_coverage = {}
    for qs_id, info in new_coverage.items():
        features_list = info.get("features", []) if isinstance(info, dict) else info
        for feat_id in features_list:
            if feat_id not in feature_coverage:
                feature_coverage[feat_id] = {"quickstarts": [], "count": 0}
            if qs_id not in feature_coverage[feat_id]["quickstarts"]:
                feature_coverage[feat_id]["quickstarts"].append(qs_id)
                feature_coverage[feat_id]["count"] = len(feature_coverage[feat_id]["quickstarts"])
    
    # Create new coverage data (replacing old data entirely)
    coverage_data = {
        "metadata": {
            "description": "Auto-generated feature coverage from published quickstarts",
            "source": "Detected from quickstart content (README, Helm values, source code)",
            "last_synced": datetime.now().isoformat(),
        },
        "coverage": new_coverage,
        "feature_coverage": feature_coverage,
    }
    
    # Save
    save_yaml(COVERAGE_FILE, coverage_data)
    
    if not quiet:
        total_features = len(set(f for feats in results.values() for f in feats))
        console.print(f"\n[green]Updated coverage.yaml: {len(results)} quickstarts, {total_features} unique features[/green]")
    
    return results


def get_coverage_freshness() -> tuple[bool, Optional[float]]:
    """Check if coverage data is fresh.
    
    Returns:
        Tuple of (is_fresh, age_in_days or None if never synced)
    """
    coverage_data = load_yaml(COVERAGE_FILE)
    metadata = coverage_data.get("metadata", {})
    last_synced = metadata.get("last_synced")
    
    if not last_synced:
        return False, None
    
    try:
        synced_dt = datetime.fromisoformat(str(last_synced))
        age = datetime.now() - synced_dt
        age_days = age.total_seconds() / 86400
        is_fresh = age_days < 7  # Consider fresh for 7 days
        return is_fresh, round(age_days, 1)
    except (ValueError, TypeError):
        return False, None
