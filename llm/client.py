# This project was developed with assistance from AI tools.
"""LLM client with automatic Langfuse tracing.

Uses Langfuse's drop-in OpenAI wrapper which automatically traces
all LLM calls. Session IDs are passed via graph config metadata.
"""

from config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
)

# Singleton client instance
_client = None


def get_client():
    """Get configured OpenAI-compatible client with automatic Langfuse tracing.
    
    Returns:
        OpenAI client instance (uses Langfuse wrapper if configured)
    """
    global _client
    
    if _client is None:
        # Use Langfuse wrapper if configured (auto-traces all LLM calls)
        if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
            from langfuse.openai import OpenAI
            _client = OpenAI(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY if LLM_API_KEY else "not-needed",
            )
        else:
            from openai import OpenAI
            _client = OpenAI(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY if LLM_API_KEY else "not-needed",
            )
    
    return _client


def get_model() -> str:
    """Get configured model name."""
    return LLM_MODEL


def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict | None = None,
) -> str:
    """Perform a chat completion.
    
    LLM calls are automatically traced by Langfuse if configured.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response
        response_format: Optional response format (e.g., {"type": "json_object"})
    
    Returns:
        The assistant's response content as a string
    """
    client = get_client()
    model = get_model()
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if response_format:
        kwargs["response_format"] = response_format
    
    response = client.chat.completions.create(**kwargs)
    
    return response.choices[0].message.content
