# This project was developed with assistance from AI tools.
"""Portfolio Analyst agent for identifying catalog blind spots.

Analyzes the overall quickstart catalog to identify gaps that customers
would expect to see but are currently missing.
"""

import logging

from agents.state import AnalysisState, PortfolioAnalysis
from llm.client import chat_completion
from llm.parsing import parse_json_response
from data import get_published_quickstarts, load_features, load_coverage

logger = logging.getLogger(__name__)


def _build_catalog_context(quickstarts: list[dict], features: list[dict], coverage: dict) -> str:
    """Build a context string describing the current quickstart catalog."""
    lines = ["## Current Quickstart Catalog\n"]
    
    for qs in quickstarts:
        name = qs.get("name", qs.get("id", "Unknown"))
        desc = qs.get("description", "No description")
        qs_id = qs.get("id", name)
        qs_features = coverage.get(qs_id, [])
        
        lines.append(f"### {name}")
        lines.append(f"Description: {desc}")
        if qs_features:
            lines.append(f"Features: {', '.join(qs_features[:8])}")
        lines.append("")
    
    # Add feature catalog summary
    lines.append("\n## Platform Features Catalog")
    feature_names = [f.get("name", f.get("id")) for f in features]
    lines.append(f"Available features: {', '.join(feature_names)}")
    
    return "\n".join(lines)


def portfolio_analyst_node(state: AnalysisState) -> dict:
    """Portfolio Analyst agent node for LangGraph.
    
    Analyzes the quickstart portfolio for blind spots and gaps.
    This runs once before individual issue analyses to inform priority scoring.
    
    LLM calls are automatically traced by Langfuse.
    """
    quickstarts = state.get("published_quickstarts", [])
    
    # Also load fresh data if not provided
    if not quickstarts:
        quickstarts = get_published_quickstarts()
    
    features = load_features()
    coverage = load_coverage()
    
    if not quickstarts:
        empty_analysis = PortfolioAnalysis(
            summary="No quickstarts found in catalog.",
            notes="Unable to analyze portfolio - catalog is empty."
        )
        return {
            "portfolio_analysis": empty_analysis,
            "portfolio_gaps": {},
        }
    
    catalog_context = _build_catalog_context(quickstarts, features, coverage)
    
    system_prompt = """You are a strategic analyst evaluating an AI quickstart catalog for a major enterprise platform (Red Hat OpenShift AI).

Your job is to identify blind spots - areas where the catalog is missing quickstarts that customers would reasonably expect to find.

## Context

Quickstarts are "portable, AI-centric demos focused on real business use cases easily deployable in Red Hat AI environments."
They should illustrate business problems anyone can understand, not just technical implementations.
The goal is to show customers what's possible, not to teach them how to build it.

## Analysis Framework

Consider these dimensions when identifying gaps:

1. **Industry Verticals**: Which major industries are underserved?
   - Healthcare, Financial Services, Retail, Manufacturing, Government, Education, Media, Telecom, etc.
   
2. **Common AI Use Cases**: What AI applications do customers frequently ask about?
   - Document processing, customer service, fraud detection, predictive maintenance, content generation, etc.
   
3. **Business Functions**: What business processes benefit from AI?
   - Sales, Marketing, HR, Legal, Operations, Finance, Customer Support, etc.
   
4. **Technical Capabilities**: What AI techniques should be demonstrated?
   - Computer vision, speech/audio, time series, recommendation systems, anomaly detection, etc.
   
5. **Adjacent Expectations**: If a customer sees one quickstart, what related ones would they expect?

## Response Format

Respond with ONLY a JSON object:

```json
{
    "underserved_industries": [
        "Industry name: Brief explanation of what's missing (10-15 words)"
    ],
    "missing_use_cases": [
        "Use case: Brief explanation of why customers might expect this (10-15 words)"
    ],
    "undemonstrated_capabilities": [
        "Capability: Brief explanation of the gap (10-15 words)"
    ],
    "expected_adjacencies": [
        "Given [existing quickstart], customers would expect: [missing adjacent quickstart]"
    ],
    "summary": "2-3 sentence executive summary of notable gaps",
    "notes": "Any additional observations about portfolio balance or strategy"
}
```

## Tone

Use measured, matter-of-fact language. Avoid dramatic or emphatic words like "critical", "dangerous", "heavily", "alarming", "glaring", "severely", "desperately", or "urgent". Simply note what is absent and why it would be expected - the observations speak for themselves without added emphasis.

Be specific and actionable. Focus on gaps that would be relevant to enterprise customers evaluating the platform."""

    user_prompt = f"""{catalog_context}

---

Analyze this quickstart catalog and identify blind spots - areas where customers would reasonably expect to find quickstarts but currently don't.

Focus on:
1. Major industries with little or no representation
2. Common AI use cases that aren't demonstrated
3. Technical capabilities that should be showcased
4. Natural adjacencies to existing quickstarts that are missing

Remember: Quickstarts should be business-focused demos that anyone can understand, not just technical tutorials."""

    try:
        response = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=2000,
        )
        
        result = parse_json_response(response, {})
        
        analysis = PortfolioAnalysis(
            underserved_industries=result.get("underserved_industries", []),
            missing_use_cases=result.get("missing_use_cases", []),
            undemonstrated_capabilities=result.get("undemonstrated_capabilities", []),
            expected_adjacencies=result.get("expected_adjacencies", []),
            summary=result.get("summary", ""),
            notes=result.get("notes", ""),
        )
        
        # Extract gaps in structured format for priority scoring
        gaps = {
            "industries": analysis.underserved_industries,
            "use_cases": analysis.missing_use_cases,
            "capabilities": analysis.undemonstrated_capabilities,
        }
        
        return {
            "portfolio_analysis": analysis,
            "portfolio_gaps": gaps,
        }
        
    except Exception as e:
        logger.error("Portfolio analysis failed: %s", e)
        error_analysis = PortfolioAnalysis(
            summary=f"Analysis failed: {str(e)}",
            notes="Unable to complete portfolio analysis due to an error."
        )
        return {
            "portfolio_analysis": error_analysis,
            "portfolio_gaps": {},
            "errors": [f"Portfolio Analyst error: {str(e)}"],
        }


def portfolio_analysis_to_dict(analysis: PortfolioAnalysis) -> dict:
    """Convert PortfolioAnalysis to dictionary for serialization."""
    return {
        "underserved_industries": analysis.underserved_industries,
        "missing_use_cases": analysis.missing_use_cases,
        "undemonstrated_capabilities": analysis.undemonstrated_capabilities,
        "expected_adjacencies": analysis.expected_adjacencies,
        "summary": analysis.summary,
        "notes": analysis.notes,
    }


def dict_to_portfolio_analysis(data: dict) -> PortfolioAnalysis:
    """Convert dictionary to PortfolioAnalysis."""
    return PortfolioAnalysis(
        underserved_industries=data.get("underserved_industries", []),
        missing_use_cases=data.get("missing_use_cases", []),
        undemonstrated_capabilities=data.get("undemonstrated_capabilities", []),
        expected_adjacencies=data.get("expected_adjacencies", []),
        summary=data.get("summary", ""),
        notes=data.get("notes", ""),
    )
