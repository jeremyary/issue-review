# This project was developed with assistance from AI tools.
"""Data collection module for fetching GitHub issues, repositories, and quickstart catalog."""

import json
import os
import subprocess
import time
from typing import Optional

import requests

from config import (
    CACHE_DIR,
    CACHE_TTL_SECONDS,
    GITHUB_ORG,
    GITHUB_REPO,
    GITHUB_TOKEN,
    ISSUE_PREFIX,
)
from data import get_published_quickstarts as _get_catalog_quickstarts


def _get_headers() -> dict:
    """Get headers for GitHub API requests."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def _cache_path(name: str) -> str:
    """Get the cache file path for a given name."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{name}.json")


def _load_cache(name: str) -> Optional[dict | list]:
    """Load data from cache if available and not expired."""
    path = _cache_path(name)
    if os.path.exists(path):
        with open(path, "r") as f:
            cached = json.load(f)
        
        if isinstance(cached, dict) and "cached_at" in cached and "data" in cached:
            age = time.time() - cached["cached_at"]
            if age < CACHE_TTL_SECONDS:
                return cached["data"]
        return None
    return None


def _save_cache(name: str, data: dict | list) -> None:
    """Save data to cache with timestamp."""
    path = _cache_path(name)
    cached = {
        "cached_at": time.time(),
        "data": data,
    }
    with open(path, "w") as f:
        json.dump(cached, f, indent=2)


def fetch_quickstart_issues(bypass_cache: bool = False) -> list[dict]:
    """Fetch all open issues with the quickstart suggestion prefix."""
    cache_name = "issues"
    
    if not bypass_cache:
        cached = _load_cache(cache_name)
        if cached:
            return cached
    
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{GITHUB_ORG}/{GITHUB_REPO}/issues",
                "--paginate",
                "-q", f'.[] | select(.title | startswith("{ISSUE_PREFIX}")) | {{number, title, body, html_url, user: .user.login, created_at}}'
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        issues = []
        for line in result.stdout.strip().split("\n"):
            if line:
                issues.append(json.loads(line))
        
        _save_cache(cache_name, issues)
        return issues
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    issues = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.github.com/repos/{GITHUB_ORG}/{GITHUB_REPO}/issues"
        params = {"state": "open", "per_page": per_page, "page": page}
        
        response = requests.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        
        page_issues = response.json()
        if not page_issues:
            break
        
        for issue in page_issues:
            if issue.get("title", "").startswith(ISSUE_PREFIX):
                issues.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue.get("body", ""),
                    "html_url": issue["html_url"],
                    "user": issue["user"]["login"],
                    "created_at": issue["created_at"],
                })
        
        page += 1
    
    _save_cache(cache_name, issues)
    return issues


def fetch_org_repositories(bypass_cache: bool = False) -> list[dict]:
    """Fetch all repositories from the GitHub organization."""
    cache_name = "repositories"
    
    if not bypass_cache:
        cached = _load_cache(cache_name)
        if cached:
            return cached
    
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"orgs/{GITHUB_ORG}/repos",
                "--paginate",
                "-q", '.[] | {name, description, html_url, topics}'
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        repos = []
        for line in result.stdout.strip().split("\n"):
            if line:
                repos.append(json.loads(line))
        
        _save_cache(cache_name, repos)
        return repos
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    repos = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"
        params = {"per_page": per_page, "page": page}
        
        response = requests.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        
        page_repos = response.json()
        if not page_repos:
            break
        
        for repo in page_repos:
            repos.append({
                "name": repo["name"],
                "description": repo.get("description", ""),
                "html_url": repo["html_url"],
                "topics": repo.get("topics", []),
            })
        
        page += 1
    
    _save_cache(cache_name, repos)
    return repos


def get_published_quickstarts() -> list[dict]:
    """Get the list of published quickstarts from the catalog.
    
    Loads from data/catalog.yaml.
    """
    return _get_catalog_quickstarts()


def get_issue_by_number(issue_number: int, issues: list[dict] = None, bypass_cache: bool = False) -> Optional[dict]:
    """Get a specific issue by number."""
    if issues:
        for issue in issues:
            if issue["number"] == issue_number:
                return issue
        return None
    
    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{GITHUB_ORG}/{GITHUB_REPO}/issues/{issue_number}",
                "-q", '{number, title, body, html_url, user: .user.login, created_at}'
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    url = f"https://api.github.com/repos/{GITHUB_ORG}/{GITHUB_REPO}/issues/{issue_number}"
    response = requests.get(url, headers=_get_headers())
    
    if response.status_code == 200:
        issue = response.json()
        return {
            "number": issue["number"],
            "title": issue["title"],
            "body": issue.get("body", ""),
            "html_url": issue["html_url"],
            "user": issue["user"]["login"],
            "created_at": issue["created_at"],
        }
    
    return None
