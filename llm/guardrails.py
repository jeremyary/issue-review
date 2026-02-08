# This project was developed with assistance from AI tools.
"""
Content safety validation using LLM-based guardrails.

Provides validation for:
- Harmful or inappropriate content
- Hallucinations (claims not supported by context)
- Professional tone
- On-topic responses
"""

from dataclasses import dataclass

from llm.client import get_client, get_model
from prompts import SAFETY_CHECK_SYSTEM_PROMPT


@dataclass
class GuardrailResult:
    """Result of a guardrail safety check."""
    is_safe: bool
    category: str | None = None
    reason: str | None = None


def check_output_safety(
    content: str,
    context: str | None = None,
) -> GuardrailResult:
    """Check if generated content passes safety guardrails.
    
    Uses LLM to validate content for safety, accuracy, and professionalism.
    Fails open (allows content through) if the check itself fails.
    
    Args:
        content: The generated content to check
        context: Optional context for hallucination detection
    
    Returns:
        GuardrailResult with safety status and details
    """
    client = get_client()
    model = get_model()
    
    user_message = f"Content to evaluate:\n{content}"
    if context:
        user_message = f"Context:\n{context}\n\n{user_message}"
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SAFETY_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            max_tokens=100,
        )
        
        result = (response.choices[0].message.content or "").strip()
        
        if "|" in result:
            category, reason = result.split("|", 1)
            category = category.strip().lower()
        else:
            category = result.strip().lower()
            reason = None
        
        return GuardrailResult(
            is_safe=(category == "safe"),
            category=category,
            reason=reason.strip() if reason else None,
        )
    
    except Exception as e:
        # Fail-open for availability, but provide error context
        return GuardrailResult(
            is_safe=True,
            category="error",
            reason=f"Guardrail check failed: {str(e)}",
        )


def validate_coordinator_summary(summary: str) -> GuardrailResult:
    """Validate Coordinator's final summary for professional tone."""
    return check_output_safety(
        content=summary,
        context="This is a professional analysis summary for maintainers reviewing quickstart suggestions.",
    )
