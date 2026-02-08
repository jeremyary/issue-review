# This project was developed with assistance from AI tools.
"""Catalog sync utilities for refreshing data from GitHub."""

import os
import re
import subprocess
from datetime import datetime
from typing import Optional

import requests
from rich.console import Console

from config import GITHUB_ORG, GITHUB_TOKEN, CATALOG_STALE_DAYS
from data import (
    load_catalog,
    get_catalog_last_synced,
    DATA_DIR,
    CATALOG_FILE,
    save_yaml,
)

console = Console()

# Directory for cloned repos
REPOS_DIR = os.path.join(DATA_DIR, "repos")

# The canonical source for published quickstarts
PUBLISHED_QUICKSTARTS_REPO = "ai-quickstart-pub"
PUBLISHED_QUICKSTARTS_PATH = "quickstart"


def fetch_published_quickstarts() -> list[dict]:
    """Fetch the list of officially published quickstarts from ai-quickstart-pub.
    
    Published quickstarts are tracked as git submodules in the ai-quickstart-pub
    repository's quickstart/ directory. This is the authoritative source.
    
    Returns:
        List of dicts with repo info: {"name": str, "url": str, "description": str}
    """
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    # Fetch the .gitmodules file to get submodule URLs
    gitmodules_url = f"https://raw.githubusercontent.com/{GITHUB_ORG}/{PUBLISHED_QUICKSTARTS_REPO}/main/.gitmodules"
    
    try:
        response = requests.get(gitmodules_url, headers=headers, timeout=30)
        response.raise_for_status()
        gitmodules_content = response.text
    except requests.RequestException as e:
        console.print(f"[red]Failed to fetch .gitmodules: {e}[/]")
        return []
    
    # Parse .gitmodules to extract submodule info
    # Format: [submodule "quickstart/name"] path = ... url = ...
    quickstarts = []
    
    # Match submodule blocks
    submodule_pattern = r'\[submodule "quickstart/([^"]+)"\][^\[]*url\s*=\s*(\S+)'
    matches = re.findall(submodule_pattern, gitmodules_content, re.DOTALL)
    
    for name, url in matches:
        # Clean up URL (remove .git suffix if present)
        repo_url = url.strip()
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Extract repo name from URL
        repo_name = repo_url.split('/')[-1]
        
        quickstarts.append({
            "name": repo_name,
            "url": repo_url,
        })
    
    # Fetch descriptions from GitHub API for each repo
    for qs in quickstarts:
        try:
            repo_api_url = f"https://api.github.com/repos/{GITHUB_ORG}/{qs['name']}"
            resp = requests.get(repo_api_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                repo_data = resp.json()
                qs["description"] = repo_data.get("description", "")
        except requests.RequestException:
            qs["description"] = ""
    
    return quickstarts


def check_catalog_freshness() -> tuple[bool, Optional[int]]:
    """Check if the catalog is fresh (within staleness threshold).
    
    Returns:
        Tuple of (is_fresh, age_in_days). age_in_days is None if never synced.
    """
    last_synced = get_catalog_last_synced()
    
    if last_synced is None:
        return False, None
    
    age = datetime.now() - last_synced
    age_days = age.days
    
    return age_days < CATALOG_STALE_DAYS, age_days


def ensure_catalog_fresh(force: bool = False, quiet: bool = False) -> bool:
    """Ensure catalog is fresh, syncing if needed.
    
    Args:
        force: Force sync even if catalog is fresh
        quiet: Suppress output messages
    
    Returns:
        True if sync was performed, False if skipped (already fresh)
    """
    if not force:
        is_fresh, age_days = check_catalog_freshness()
        
        if is_fresh:
            if not quiet:
                console.print(f"[dim]Catalog is {age_days} day(s) old (threshold: {CATALOG_STALE_DAYS} days)[/]")
            return False
        
        if age_days is None:
            if not quiet:
                console.print("[yellow]Catalog has never been synced, running initial sync...[/]")
        else:
            if not quiet:
                console.print(f"[yellow]Catalog is {age_days} day(s) old (threshold: {CATALOG_STALE_DAYS} days), syncing...[/]")
    
    return sync_catalog(quiet=quiet)


def sync_catalog(quiet: bool = False) -> bool:
    """Sync the catalog from the official published quickstarts source.
    
    Published quickstarts are sourced from the ai-quickstart-pub repository,
    which tracks official quickstarts as git submodules. This ensures we only
    include quickstarts that have been officially published, not all repos
    in the organization.
    
    Args:
        quiet: Suppress output messages
    
    Returns:
        True if sync succeeded, False otherwise
    """
    try:
        if not quiet:
            console.print("[blue]Syncing catalog from published quickstarts...[/]")
        
        # Fetch only published quickstarts (from ai-quickstart-pub submodules)
        published = fetch_published_quickstarts()
        
        if not published:
            if not quiet:
                console.print("[red]No published quickstarts found[/]")
            return False
        
        if not quiet:
            console.print(f"  Found {len(published)} published quickstart(s)")
        
        # Build new catalog from published quickstarts (replace, don't append)
        # This ensures we only have officially published quickstarts
        quickstarts = []
        for repo in published:
            repo_name = repo.get("name", "")
            quickstarts.append({
                "id": repo_name,
                "name": repo_name.replace("-", " ").title(),
                "repo": repo_name,
                "description": repo.get("description", ""),
                "url": repo.get("url", f"https://github.com/{GITHUB_ORG}/{repo_name}"),
            })
        
        # Create catalog with metadata
        catalog = {
            "metadata": {
                "description": "Official published quickstarts from ai-quickstart-pub",
                "source": f"https://github.com/{GITHUB_ORG}/{PUBLISHED_QUICKSTARTS_REPO}",
                "last_synced": datetime.now().isoformat(),
            },
            "quickstarts": quickstarts,
        }
        
        save_yaml(CATALOG_FILE, catalog)
        
        if not quiet:
            console.print(f"  [green]Catalog updated with {len(quickstarts)} published quickstart(s)[/]")
            for qs in quickstarts:
                console.print(f"    • {qs['repo']}")
        
        return True
        
    except Exception as e:
        if not quiet:
            console.print(f"[red]Sync failed: {e}[/]")
        return False


def clone_or_pull_repo(repo_name: str, quiet: bool = False) -> Optional[str]:
    """Clone or pull a repository.
    
    Args:
        repo_name: Name of the repo to clone/pull
        quiet: Suppress output messages
    
    Returns:
        Path to the repo directory, or None if failed
    """
    os.makedirs(REPOS_DIR, exist_ok=True)
    repo_path = os.path.join(REPOS_DIR, repo_name)
    repo_url = f"https://github.com/{GITHUB_ORG}/{repo_name}.git"
    
    try:
        if os.path.exists(repo_path):
            # Pull latest
            if not quiet:
                console.print(f"  Pulling {repo_name}...")
            subprocess.run(
                ["git", "-C", repo_path, "pull", "--quiet"],
                capture_output=True,
                check=True,
            )
        else:
            # Clone (shallow for speed)
            if not quiet:
                console.print(f"  Cloning {repo_name}...")
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", repo_url, repo_path],
                capture_output=True,
                check=True,
            )
        
        return repo_path
        
    except subprocess.CalledProcessError as e:
        if not quiet:
            console.print(f"  [red]Failed to clone/pull {repo_name}: {e}[/]")
        return None


def sync_content(quickstart_ids: list[str] | None = None, quiet: bool = False) -> dict:
    """Sync content for quickstarts (clone repos, extract content).
    
    This is a heavier operation that clones repos and extracts content
    for indexing. Use sync_catalog() for lightweight metadata refresh.
    
    Args:
        quickstart_ids: List of quickstart IDs to sync, or None for all
        quiet: Suppress output messages
    
    Returns:
        Dict with sync results {quickstart_id: {"success": bool, "path": str}}
    """
    catalog = load_catalog()
    quickstarts = catalog.get("quickstarts", [])
    
    if quickstart_ids:
        quickstarts = [qs for qs in quickstarts if qs.get("id") in quickstart_ids]
    
    results = {}
    
    for qs in quickstarts:
        repo_name = qs.get("repo")
        qs_id = qs.get("id", repo_name)
        
        if not repo_name:
            continue
        
        repo_path = clone_or_pull_repo(repo_name, quiet=quiet)
        
        results[qs_id] = {
            "success": repo_path is not None,
            "path": repo_path,
        }
    
    return results
