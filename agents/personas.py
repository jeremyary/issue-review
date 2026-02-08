# This project was developed with assistance from AI tools.
"""
Persona Panel agent for broad appeal evaluation.

Responsibilities:
- Run multiple persona evaluations in parallel
- Assess if non-technical professionals would understand/use the quickstart
- Determine overall broad appeal classification
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.state import (
    AnalysisState,
    BroadAppealAnalysis,
    PersonaEvaluation,
    BroadAppeal,
)
from llm.client import chat_completion
from llm.parsing import parse_json_response
from data import load_personas
from prompts import PERSONA_EVALUATION_USER_PROMPT


def evaluate_with_persona(
    persona: dict,
    issue_title: str,
    issue_body: str,
) -> PersonaEvaluation:
    """Run a single persona evaluation.
    
    Each persona evaluates from their professional perspective
    whether the quickstart would be relevant to their work.
    
    LLM calls are automatically traced by Langfuse.
    """
    persona_id = persona.get("id", "unknown")
    persona_name = persona.get("name", "Unknown Persona")
    
    system_prompt = persona.get("system_prompt", "")
    user_prompt = PERSONA_EVALUATION_USER_PROMPT.format(
        title=issue_title,
        body=issue_body[:5000],  # Truncate for persona evaluation
    )
    
    try:
        response = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        
        result = _parse_persona_response(response)
        
        return PersonaEvaluation(
            persona_id=persona_id,
            persona_name=persona_name,
            professionally_relevant=result.get("professionally_relevant", False),
            relevance=result.get("relevance", "NONE"),
            explanation=result.get("explanation", ""),
        )
    
    except Exception as e:
        return PersonaEvaluation(
            persona_id=persona_id,
            persona_name=persona_name,
            professionally_relevant=False,
            relevance="NONE",
            explanation=f"Evaluation failed: {str(e)}",
        )


def _parse_persona_response(content: str) -> dict:
    """Parse JSON from persona response with text fallback."""
    result = parse_json_response(content)
    if result:
        return result
    
    # Fallback: extract relevance from plain text
    content_upper = content.upper()
    relevance = "NONE"
    if "HIGH" in content_upper:
        relevance = "HIGH"
    elif "MEDIUM" in content_upper:
        relevance = "MEDIUM"
    elif "LOW" in content_upper:
        relevance = "LOW"
    
    return {
        "professionally_relevant": relevance in ("HIGH", "MEDIUM"),
        "relevance": relevance,
        "explanation": content[:200] if content else "Unable to parse response",
    }


def determine_broad_appeal(evaluations: list[PersonaEvaluation]) -> BroadAppeal:
    """Classify overall broad appeal from persona evaluations.
    
    Classification logic:
    - UNIVERSAL: 4+ personas find it relevant, or 3+ rate it HIGH
    - BUSINESS_SPECIFIC: 2+ personas find it relevant
    - TECHNICAL_ONLY: Less than 2 personas find it relevant
    """
    if not evaluations:
        return BroadAppeal.TECHNICAL_ONLY
    
    high_relevance = sum(1 for e in evaluations if e.relevance == "HIGH")
    medium_relevance = sum(1 for e in evaluations if e.relevance == "MEDIUM")
    relevant_count = high_relevance + medium_relevance
    
    if relevant_count >= 4 or high_relevance >= 3:
        return BroadAppeal.UNIVERSAL
    elif relevant_count >= 2:
        return BroadAppeal.BUSINESS_SPECIFIC
    else:
        return BroadAppeal.TECHNICAL_ONLY


def persona_panel_node(state: AnalysisState) -> dict:
    """Persona Panel agent node for LangGraph.
    
    Runs all persona evaluations in parallel for efficiency.
    Each persona independently assesses the quickstart from their
    professional perspective.
    
    LLM calls are automatically traced by Langfuse.
    """
    issue = state.get("issue", {})
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    
    personas = load_personas()
    if not personas:
        return {
            "broad_appeal_analysis": BroadAppealAnalysis(
                summary="No personas configured for evaluation."
            ),
            "errors": ["Persona Panel: No personas found in data/personas.yaml"],
        }
    
    # Run persona evaluations in parallel
    evaluations: list[PersonaEvaluation] = []
    errors: list[str] = []
    
    with ThreadPoolExecutor(max_workers=len(personas)) as executor:
        futures = {
            executor.submit(
                evaluate_with_persona,
                persona,
                title,
                body,
            ): persona
            for persona in personas
        }
        
        for future in as_completed(futures):
            persona = futures[future]
            try:
                evaluation = future.result()
                evaluations.append(evaluation)
            except Exception as e:
                errors.append(f"Persona '{persona.get('id')}' failed: {str(e)}")
    
    # Aggregate results
    broad_appeal = determine_broad_appeal(evaluations)
    
    personas_who_understand = [
        e.persona_name for e in evaluations
        if e.relevance in ("HIGH", "MEDIUM")
    ]
    personas_who_dont = [
        e.persona_name for e in evaluations
        if e.relevance in ("LOW", "NONE")
    ]
    
    # Build summary (brief classification only - details shown separately)
    if broad_appeal == BroadAppeal.UNIVERSAL:
        summary = "This quickstart has broad professional appeal."
    elif broad_appeal == BroadAppeal.BUSINESS_SPECIFIC:
        summary = "This quickstart appeals to specific business domains."
    else:
        summary = "This quickstart is primarily technical in nature."
    
    result = {
        "broad_appeal_analysis": BroadAppealAnalysis(
            broad_appeal=broad_appeal,
            personas_who_understand=personas_who_understand,
            personas_who_dont=personas_who_dont,
            evaluations=evaluations,
            summary=summary,
        )
    }
    
    if errors:
        result["errors"] = errors
    
    return result
