# This project was developed with assistance from AI tools.
"""Main LangGraph workflow for multi-agent analysis."""

import logging

from langgraph.graph import StateGraph, START, END

from agents.state import AnalysisState, FinalAnalysis
from agents.technical import technical_analyst_node
from agents.personas import persona_panel_node
from agents.platform import platform_specialist_node
from agents.coordinator import coordinator_node
from llm.callbacks import get_langfuse_handler, is_langfuse_configured, flush_langfuse

logger = logging.getLogger(__name__)


def create_analysis_graph(
    include_personas: bool = True,
    include_platform: bool = True,
) -> StateGraph:
    """Create the main analysis workflow graph.
    
    All specialist agents run in parallel, then results flow to Coordinator.
    """
    workflow = StateGraph(AnalysisState)
    
    # Add core nodes
    workflow.add_node("technical_analyst", technical_analyst_node)
    workflow.add_node("coordinator", coordinator_node)
    
    # Track which nodes need to complete before coordinator
    pre_coordinator_nodes = ["technical_analyst"]
    
    # Add optional nodes
    if include_personas:
        workflow.add_node("persona_panel", persona_panel_node)
        pre_coordinator_nodes.append("persona_panel")
    
    if include_platform:
        workflow.add_node("platform_specialist", platform_specialist_node)
        pre_coordinator_nodes.append("platform_specialist")
    
    # Wire up parallel execution from START
    for node in pre_coordinator_nodes:
        workflow.add_edge(START, node)
        workflow.add_edge(node, "coordinator")
    
    workflow.add_edge("coordinator", END)
    
    return workflow.compile()


def analyze_issue(
    issue: dict,
    published_quickstarts: list[dict],
    org_repos: list[dict],
    feature_catalog: list[dict] | None = None,
    portfolio_gaps: dict | None = None,
    include_personas: bool = True,
    include_platform: bool = True,
) -> FinalAnalysis:
    """Run the multi-agent analysis on an issue.
    
    Args:
        issue: GitHub issue data
        published_quickstarts: List of existing quickstarts
        org_repos: List of organization repositories
        feature_catalog: Optional list of platform features
        portfolio_gaps: Optional dict with catalog gaps for priority boosting
            {industries: [], use_cases: [], capabilities: []}
        include_personas: Whether to run persona panel analysis
        include_platform: Whether to run platform specialist analysis
    
    Langfuse tracing is automatic:
    - LangGraph callback handler traces workflow execution
    - Langfuse OpenAI wrapper traces all LLM calls
    - Session ID (via metadata) groups all traces for this issue together
    """
    # Generate session ID from issue number for trace grouping
    issue_number = issue.get("number", "unknown")
    session_id = f"issue-{issue_number}"
    
    graph = create_analysis_graph(
        include_personas=include_personas,
        include_platform=include_platform,
    )
    
    # Build initial state
    initial_state: AnalysisState = {
        "issue": issue,
        "published_quickstarts": published_quickstarts,
        "org_repos": org_repos,
        "feature_catalog": feature_catalog or [],
        "portfolio_gaps": portfolio_gaps or {},
        "errors": [],
    }
    
    # Build config with Langfuse callback and session metadata
    config = {}
    langfuse_handler = get_langfuse_handler()
    
    if langfuse_handler and is_langfuse_configured():
        # Use metadata to pass session_id (recommended approach per Langfuse docs)
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {
            "langfuse_session_id": session_id,
            "langfuse_tags": ["issue-analysis"],
        }
        logger.debug(
            "Langfuse tracing enabled for issue #%s (session_id: %s)",
            issue_number, session_id
        )
    else:
        logger.debug("Langfuse tracing not configured, running without tracing")
    
    try:
        result = graph.invoke(initial_state, config=config)
        logger.debug(
            "Analysis complete for issue #%s (session_id: %s)",
            issue_number, session_id
        )
        return result.get("final_analysis") or FinalAnalysis()
    finally:
        flush_langfuse()
