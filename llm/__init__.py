# This project was developed with assistance from AI tools.
"""LLM client and utilities."""

from llm.client import (
    get_client,
    get_model,
    chat_completion,
)
from llm.callbacks import (
    get_langfuse_handler,
    get_langfuse_client,
    is_langfuse_configured,
    flush_langfuse,
)
from llm.tools import (
    Tool,
    ToolCall,
    ToolResult,
    tools_to_openai_format,
    parse_tool_calls,
    execute_tool,
    execute_tools,
    tool_results_to_messages,
    chat_with_tools,
)

__all__ = [
    "get_client",
    "get_model",
    "chat_completion",
    # Langfuse tracing
    "get_langfuse_handler",
    "get_langfuse_client",
    "is_langfuse_configured",
    "flush_langfuse",
    # Tool-calling infrastructure
    "Tool",
    "ToolCall",
    "ToolResult",
    "tools_to_openai_format",
    "parse_tool_calls",
    "execute_tool",
    "execute_tools",
    "tool_results_to_messages",
    "chat_with_tools",
]
