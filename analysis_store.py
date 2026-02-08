# This project was developed with assistance from AI tools.
"""Persistence layer for storing and retrieving issue analyses."""

import json
import os
import threading
from datetime import datetime
from typing import Optional

from config import CACHE_DIR

ANALYSIS_STORE_FILE = os.path.join(CACHE_DIR, "analyses.json")
PORTFOLIO_STORE_FILE = os.path.join(CACHE_DIR, "portfolio_analysis.json")

# Lock for thread-safe read-modify-write on the store file
_store_lock = threading.Lock()


def _ensure_cache_dir():
    """Ensure the cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_analysis_store() -> dict:
    """Load all stored analyses from disk."""
    _ensure_cache_dir()
    if os.path.exists(ANALYSIS_STORE_FILE):
        with open(ANALYSIS_STORE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_analysis_store(store: dict):
    """Save analyses to disk."""
    _ensure_cache_dir()
    with open(ANALYSIS_STORE_FILE, "w") as f:
        json.dump(store, f, indent=2)


def get_cached_analysis(issue_number: int) -> Optional[dict]:
    """Get cached analysis for an issue if it exists."""
    with _store_lock:
        store = load_analysis_store()
        return store.get(str(issue_number))


def cache_analysis(issue_number: int, analysis_dict: dict, issue_title: str = ""):
    """Store an analysis result for an issue."""
    with _store_lock:
        store = load_analysis_store()
        store[str(issue_number)] = {
            "issue_number": issue_number,
            "issue_title": issue_title,
            "analysis": analysis_dict,
            "analyzed_at": datetime.now().isoformat(),
        }
        save_analysis_store(store)


def clear_analysis_store():
    """Clear all stored analyses (issues and portfolio)."""
    _ensure_cache_dir()
    if os.path.exists(ANALYSIS_STORE_FILE):
        os.remove(ANALYSIS_STORE_FILE)
    if os.path.exists(PORTFOLIO_STORE_FILE):
        os.remove(PORTFOLIO_STORE_FILE)


def get_all_cached_analyses() -> dict:
    """Get all cached analyses."""
    return load_analysis_store()


# --- Portfolio analysis cache ---

def get_cached_portfolio() -> Optional[dict]:
    """Get cached portfolio analysis if it exists."""
    _ensure_cache_dir()
    if os.path.exists(PORTFOLIO_STORE_FILE):
        with open(PORTFOLIO_STORE_FILE, "r") as f:
            return json.load(f)
    return None


def cache_portfolio(portfolio_dict: dict, gaps: dict):
    """Store a portfolio analysis result."""
    _ensure_cache_dir()
    data = {
        "portfolio": portfolio_dict,
        "gaps": gaps,
        "analyzed_at": datetime.now().isoformat(),
    }
    with open(PORTFOLIO_STORE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def clear_portfolio_cache():
    """Clear the cached portfolio analysis."""
    _ensure_cache_dir()
    if os.path.exists(PORTFOLIO_STORE_FILE):
        os.remove(PORTFOLIO_STORE_FILE)
