# This project was developed with assistance from AI tools.
"""
Technical Analyst agent for evaluating quickstart suggestions.

Responsibilities:
- Assess use case overlap with existing quickstarts
- Determine development maturity (code, plan, concept)
- Identify similar technology stacks
- Discover adjacent gaps the proposal could fill
"""

from agents.state import (
    AnalysisState,
    TechnicalAnalysis,
    OverlapLevel,
    DevelopmentStage,
)
from llm.client import get_client, get_model, chat_completion
from llm.tools import chat_with_tools
from llm.parsing import parse_json_response
from config import GITHUB_ORG, EXCLUDED_REPOS, ISSUE_PREFIX
from prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_USER_PROMPT,
    TECHNICAL_ANALYST_SYSTEM_PROMPT,
    TECHNICAL_ANALYST_USER_PROMPT,
)
from tools.research import (
    semantic_search_tool,
    get_quickstart_readme_tool,
    find_similar_quickstarts_tool,
    get_quickstart_code_tool,
)

# Default response structure for parsing failures
_DEFAULT_RESPONSE = {
    "overlap_level": "UNCLEAR",
    "development_stage": "CONCEPT_SUMMARY",
    "use_case_overlap": [],
    "similar_stack": [],
    "summary": "Unable to parse analysis. Please review manually.",
}

# Tools available to this agent
_TOOLS = [
    semantic_search_tool,
    get_quickstart_readme_tool,
    find_similar_quickstarts_tool,
    get_quickstart_code_tool,
]


def strip_issue_prefix(title: str) -> str:
    """Remove the quickstart suggestion prefix from a title."""
    if title.startswith(ISSUE_PREFIX):
        return title[len(ISSUE_PREFIX):].strip()
    return title


def build_quickstarts_context(quickstarts: list[dict]) -> str:
    """Format quickstart catalog entries for prompt context."""
    entries = []
    for qs in quickstarts:
        lines = [
            f"### {qs['name']} (repo: {qs.get('repo', 'N/A')})",
            f"- **Description**: {qs['description']}",
        ]
        if qs.get('pattern'):
            lines.append(f"- **Pattern**: {qs['pattern']}")
        if qs.get('industry'):
            lines.append(f"- **Industry**: {qs['industry']}")
        if qs.get('technologies'):
            lines.append(f"- **Technologies**: {', '.join(qs['technologies'])}")
        if qs.get('unique_features'):
            lines.append(f"- **Unique Features**: {qs['unique_features']}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries)


def build_repos_context(repos: list[dict]) -> str:
    """Format organization repository list for prompt context."""
    return "\n".join([
        f"- **{repo['name']}**: {repo.get('description', 'No description') or 'No description'}"
        for repo in repos
        if repo['name'] not in EXCLUDED_REPOS
    ][:20])


def _needs_clarification(overlap_level: OverlapLevel, dev_stage: DevelopmentStage) -> bool:
    """Check if clarification is needed based on overlap level and development stage.
    
    Clarification is NOT needed only when BOTH conditions are met:
    1. overlap_level is UNIQUE or POSSIBLE_OVERLAP (not UNCLEAR)
    2. development_stage is HAS_CODE or DETAILED_PLAN
    """
    overlap_clear = overlap_level in (OverlapLevel.UNIQUE, OverlapLevel.POSSIBLE_OVERLAP)
    stage_mature = dev_stage in (DevelopmentStage.HAS_CODE, DevelopmentStage.DETAILED_PLAN)
    return not (overlap_clear and stage_mature)


def _generate_default_clarification(overlap_level: OverlapLevel, dev_stage: DevelopmentStage) -> str:
    """Generate a default clarification when the LLM didn't provide one."""
    parts = []
    
    if overlap_level == OverlapLevel.UNCLEAR:
        parts.append("""
Use Case Details (to assess overlap):
- The specific problem or workflow being addressed, to help distinguish from existing quickstarts
- The intended target audience and their pain points
- Context on how the use case relates to what is already in the catalog""")
    
    if dev_stage in (DevelopmentStage.CONCEPT_SUMMARY, DevelopmentStage.DETAILED_CONCEPT):
        parts.append("""
Technical Details (to elevate to DETAILED_PLAN):
- Specific technology choices and frameworks under consideration
- The proposed architecture and component interactions
- The intended implementation approach and phasing""")
    
    return "\n".join(parts)


def _build_analysis(response: dict, fallback_note: str = "") -> TechnicalAnalysis:
    """Construct TechnicalAnalysis from parsed response."""
    summary = response.get("summary", "")
    if fallback_note:
        summary = f"({fallback_note}) {summary}"
    
    overlap_level = OverlapLevel.from_string(response.get("overlap_level", "UNCLEAR"))
    dev_stage = DevelopmentStage.from_string(response.get("development_stage", "CONCEPT_SUMMARY"))
    use_case_overlap = response.get("use_case_overlap", [])
    clarification = response.get("clarification_needed", "")
    
    # Consistency check: if use case overlaps are listed, can't be UNIQUE
    if use_case_overlap and overlap_level == OverlapLevel.UNIQUE:
        overlap_level = OverlapLevel.POSSIBLE_OVERLAP
    
    # Ensure clarification is provided when needed
    if _needs_clarification(overlap_level, dev_stage) and not clarification.strip():
        clarification = _generate_default_clarification(overlap_level, dev_stage)
    
    return TechnicalAnalysis(
        overlap_level=overlap_level,
        development_stage=dev_stage,
        use_case_overlap=use_case_overlap,
        similar_stack=response.get("similar_stack", []),
        adjacent_gaps=response.get("adjacent_gaps", []),
        clarification_needed=clarification,
        summary=summary,
    )


def technical_analyst_node(state: AnalysisState) -> dict:
    """Technical Analyst agent node for LangGraph.
    
    Uses tool-calling to search indexed content and verify overlap assessments.
    Falls back to direct prompting if tools are unavailable.
    
    LLM calls are automatically traced by Langfuse.
    """
    issue = state.get("issue", {})
    quickstarts = state.get("published_quickstarts", [])
    repos = state.get("org_repos", [])
    
    # Build context strings
    quickstarts_context = build_quickstarts_context(quickstarts)
    repos_context = build_repos_context(repos)
    
    title = strip_issue_prefix(issue.get("title", ""))
    body = issue.get("body", "") or ""
    if len(body) > 10000:
        body = body[:10000] + "\n\n[... truncated for length ...]"
    
    # Build prompts from templates
    system_prompt = TECHNICAL_ANALYST_SYSTEM_PROMPT.format(
        quickstarts_context=quickstarts_context,
        github_org=GITHUB_ORG,
        repos_context=repos_context,
    )
    user_prompt = TECHNICAL_ANALYST_USER_PROMPT.format(
        title=title,
        issue_number=issue.get('number'),
        user=issue.get('user', 'Unknown'),
        body=body,
    )
    
    try:
        # Primary path: tool-calling
        response, _ = chat_with_tools(
            client=get_client(),
            model=get_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=_TOOLS,
            max_iterations=15,
            temperature=0.3,
        )
        analysis = parse_json_response(response, _DEFAULT_RESPONSE)
        return {"technical_analysis": _build_analysis(analysis)}
    
    except Exception as e:
        # Fallback: direct prompting without tools
        return _fallback_analysis(state, str(e))


def _fallback_analysis(state: AnalysisState, error: str) -> dict:
    """Fallback to direct prompting when tool-calling fails."""
    issue = state.get("issue", {})
    quickstarts = state.get("published_quickstarts", [])
    repos = state.get("org_repos", [])
    
    quickstarts_context = build_quickstarts_context(quickstarts)
    repos_context = build_repos_context(repos)
    
    title = strip_issue_prefix(issue.get("title", ""))
    body = issue.get("body", "") or ""
    if len(body) > 15000:
        body = body[:15000] + "\n\n[... truncated for length ...]"
    
    system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
        quickstarts_info=quickstarts_context,
        github_org=GITHUB_ORG,
        repos_info=repos_context,
    )
    user_prompt = ANALYSIS_USER_PROMPT.format(
        title=title,
        issue_number=issue.get('number'),
        user=issue.get('user', 'Unknown'),
        body=body,
    )
    
    try:
        response = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        analysis = parse_json_response(response, _DEFAULT_RESPONSE)
        return {"technical_analysis": _build_analysis(analysis, f"Fallback: {error}")}
    
    except Exception as e2:
        return {
            "technical_analysis": TechnicalAnalysis(summary=f"Analysis failed: {str(e2)}"),
            "errors": [f"Technical Analyst error: {str(e2)}"],
        }
