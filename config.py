# This project was developed with assistance from AI tools.
"""Configuration settings for the issue review tool."""

import os
from dotenv import load_dotenv

load_dotenv()

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORG = "rh-ai-quickstart"
GITHUB_REPO = "ai-quickstart-contrib"
ISSUE_PREFIX = "[Quickstart suggestion]:"
EXCLUDED_REPOS = [".github", "ai-quickstart-contrib", "ai-quickstart-template"]

# LLM Configuration (OpenAI-compatible endpoint)
# Works with: OpenAI, Anthropic, local vLLM/Ollama, any OpenAI-compatible server
# Examples:
#   - Anthropic: https://api.anthropic.com/v1/
#   - OpenAI: https://api.openai.com/v1/
#   - Local vLLM: http://localhost:8000/v1/
#   - Ollama: http://localhost:11434/v1/
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5")

# LangFuse (observability)
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_TTL_SECONDS = 3600  # 1 hour TTL for issues/repos cache

# Catalog staleness threshold (days)
# Catalog auto-syncs if older than this when running analysis
CATALOG_STALE_DAYS = int(os.getenv("CATALOG_STALE_DAYS", "7"))

# PostgreSQL with pgvector (for RAG content indexing)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://issue_review:issue_review@localhost:5432/issue_review"
)
