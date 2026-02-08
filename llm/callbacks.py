# This project was developed with assistance from AI tools.
"""Langfuse observability with session-based tracing.

Uses Langfuse's drop-in OpenAI wrapper for automatic LLM call tracing
and LangChain callback handler for LangGraph workflow tracing.
Session IDs link all traces for a single analysis together.
"""

import logging
import os

from config import (
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST,
)

logger = logging.getLogger(__name__)

# Set environment variables for Langfuse SDK to pick up automatically
if LANGFUSE_PUBLIC_KEY:
    os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
if LANGFUSE_SECRET_KEY:
    os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
if LANGFUSE_HOST:
    os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST

# Singleton client instance
_langfuse_client = None


def is_langfuse_configured() -> bool:
    """Check if Langfuse is configured."""
    return bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)


def get_langfuse_client():
    """Get Langfuse client for manual operations if needed.
    
    Returns:
        Langfuse client if configured, None otherwise
    """
    global _langfuse_client
    
    if not is_langfuse_configured():
        return None
    
    if _langfuse_client is None:
        from langfuse import Langfuse
        _langfuse_client = Langfuse()
        logger.debug("Langfuse client initialized (host: %s)", LANGFUSE_HOST or "default")
    
    return _langfuse_client


def get_langfuse_handler():
    """Get Langfuse callback handler for LangGraph tracing.
    
    Note: Pass session_id via config metadata:
        config={"callbacks": [handler], "metadata": {"langfuse_session_id": "..."}}
    
    Returns:
        CallbackHandler if Langfuse is configured, None otherwise
    """
    if not is_langfuse_configured():
        return None
    
    from langfuse.langchain import CallbackHandler
    return CallbackHandler()


def flush_langfuse():
    """Flush any pending Langfuse events."""
    langfuse = get_langfuse_client()
    if langfuse:
        try:
            langfuse.flush()
            logger.debug("Langfuse events flushed")
        except Exception as e:
            logger.warning("Failed to flush Langfuse events: %s", e)
