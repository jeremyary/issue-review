# This project was developed with assistance from AI tools.
"""
Platform Specialist agent for OpenShift AI feature analysis.

Responsibilities:
- Identify which platform features a quickstart would demonstrate
- Assess platform fit (how well it showcases OpenShift AI)
- Track new vs already-demonstrated features
"""

from agents.state import (
    AnalysisState,
    PlatformAnalysis,
    PlatformFit,
)
from llm.client import chat_completion
from llm.parsing import parse_json_response
from data import load_features, get_all_demonstrated_features

# Default response structure for parsing failures
_DEFAULT_RESPONSE = {
    "features_identified": [],
    "platform_fit": "MODERATE",
    "notes": "Unable to parse platform analysis",
}

# Mapping from string to PlatformFit enum
_FIT_MAP = {
    "EXCELLENT": PlatformFit.EXCELLENT,
    "GOOD": PlatformFit.GOOD,
    "MODERATE": PlatformFit.MODERATE,
    "POOR": PlatformFit.POOR,
}


def _classify_features(
    identified: list[dict],
    valid_ids: set[str],
    demonstrated: set[str],
) -> tuple[list[str], list[str]]:
    """Separate identified features into new and reused categories."""
    new_features = []
    reused_features = []
    
    for feat in identified:
        feat_id = feat.get("id", "")
        if feat_id in valid_ids:
            if feat_id in demonstrated:
                reused_features.append(feat_id)
            else:
                new_features.append(feat_id)
    
    return new_features, reused_features


def _build_analysis(
    response: dict,
    valid_ids: set[str],
    demonstrated: set[str],
    fallback_note: str = "",
) -> PlatformAnalysis:
    """Construct PlatformAnalysis from parsed response."""
    identified = response.get("features_identified", [])
    features_new, features_reused = _classify_features(identified, valid_ids, demonstrated)
    
    platform_fit = _FIT_MAP.get(
        response.get("platform_fit", "MODERATE").upper(),
        PlatformFit.MODERATE
    )
    
    # Build notes from response
    notes_parts = []
    if fallback_note:
        notes_parts.append(f"({fallback_note})")
    if response.get("fit_explanation"):
        notes_parts.append(response["fit_explanation"])
    if response.get("notes"):
        notes_parts.append(response["notes"])
    if features_new:
        notes_parts.append(f"Would demonstrate {len(features_new)} new feature(s): {', '.join(features_new)}")
    
    return PlatformAnalysis(
        features_identified=identified,
        features_new=features_new,
        features_reused=features_reused,
        platform_fit=platform_fit,
        notes=" | ".join(notes_parts),
    )


def _build_features_context(features: list[dict], demonstrated: set[str]) -> str:
    """Build a context string describing available features and their coverage."""
    lines = ["## Available OpenShift AI Features\n"]
    
    # Group by category
    by_category = {}
    for f in features:
        cat = f.get("category", "Other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(f)
    
    for category, cat_features in by_category.items():
        lines.append(f"### {category}")
        for f in cat_features:
            fid = f["id"]
            name = f.get("name", fid)
            desc = f.get("description", "")
            coverage_status = "ALREADY DEMONSTRATED" if fid in demonstrated else "NOT YET DEMONSTRATED"
            lines.append(f"- **{fid}** ({name}): {desc} [{coverage_status}]")
        lines.append("")
    
    return "\n".join(lines)


def platform_specialist_node(state: AnalysisState) -> dict:
    """Platform Specialist agent node for LangGraph.
    
    Uses direct prompting to identify OpenShift AI features from proposals.
    
    LLM calls are automatically traced by Langfuse.
    """
    issue = state.get("issue", {})
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    
    # Load feature catalog for validation
    features = load_features()
    if not features:
        return {
            "platform_analysis": PlatformAnalysis(notes="No features catalog configured."),
            "errors": ["Platform Specialist: No features found in data/features.yaml"],
        }
    
    valid_ids = {f["id"] for f in features}
    demonstrated = get_all_demonstrated_features()
    
    # Build context with all features and their coverage status
    features_context = _build_features_context(features, demonstrated)
    
    system_prompt = """You are an OpenShift AI platform specialist analyzing quickstart proposals.

Your job is to identify which OpenShift AI features a proposed quickstart would USE or DEMONSTRATE.

## Guidelines

1. Only identify features that the proposal would actually use based on explicit mentions or clear technical requirements
2. Be conservative - if unsure whether a feature applies, don't include it
3. Use EXACT feature IDs from the catalog (e.g., "vllm", "pipelines", "rag")
4. Features marked "NOT YET DEMONSTRATED" are more valuable if this quickstart would use them

## Platform Fit Assessment

- EXCELLENT: Uses 3+ features, including at least one not yet demonstrated
- GOOD: Uses 2-3 features that align well with OpenShift AI capabilities
- MODERATE: Uses 1-2 common features
- POOR: Doesn't clearly leverage OpenShift AI platform features

## Response Format

You MUST respond with ONLY a JSON object (no other text):

```json
{
    "features_identified": [
        {"id": "feature_id", "reason": "brief explanation of why this feature would be used"}
    ],
    "platform_fit": "EXCELLENT|GOOD|MODERATE|POOR",
    "fit_explanation": "One sentence explaining the platform fit assessment"
}
```"""

    user_prompt = f"""{features_context}

---

## Quickstart Proposal to Analyze

**Title:** {title}

**Description:**
{body[:6000]}

---

Based on the proposal above, identify which OpenShift AI features would be used. Remember to respond with ONLY the JSON object."""

    try:
        response = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        analysis = parse_json_response(response, _DEFAULT_RESPONSE)
        return {"platform_analysis": _build_analysis(analysis, valid_ids, demonstrated)}
    
    except Exception as e:
        return {
            "platform_analysis": PlatformAnalysis(notes=f"Analysis failed: {str(e)}"),
            "errors": [f"Platform Specialist error: {str(e)}"],
        }
