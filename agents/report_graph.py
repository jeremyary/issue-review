# This project was developed with assistance from AI tools.
"""Report-level LangGraph workflow for multi-issue analysis.

This module orchestrates:
1. Portfolio Analyst (LangGraph node) - runs once to identify catalog gaps
2. Issue Analysis (per-issue sub-graph) - runs for each issue with gap context

The portfolio analyst runs inside its own LangGraph so it's properly traced.
Issue analysis uses the existing issue graph (agents/graph.py) in parallel,
each with its own trace session.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TypedDict, Annotated
from dataclasses import dataclass
import operator

from langgraph.graph import StateGraph, START, END

from agents.state import PortfolioAnalysis, FinalAnalysis
from agents.portfolio import portfolio_analyst_node
from agents.graph import analyze_issue
from llm.callbacks import get_langfuse_handler, is_langfuse_configured, flush_langfuse

logger = logging.getLogger(__name__)


@dataclass
class IssueResult:
    """Result of analyzing a single issue."""
    issue_number: int
    issue_title: str
    analysis: FinalAnalysis
    analyzed_at: str = ""


class PortfolioState(TypedDict, total=False):
    """State for the portfolio analysis graph."""
    # Input
    published_quickstarts: list[dict]
    
    # Output
    portfolio_analysis: PortfolioAnalysis | None
    portfolio_gaps: dict
    
    # Error tracking
    errors: Annotated[list[str], operator.add]


def _portfolio_analyst_adapter(state: PortfolioState) -> dict:
    """Adapter to run portfolio analyst within the portfolio graph."""
    analyst_state = {
        "published_quickstarts": state.get("published_quickstarts", []),
    }
    
    result = portfolio_analyst_node(analyst_state)
    
    return {
        "portfolio_analysis": result.get("portfolio_analysis"),
        "portfolio_gaps": result.get("portfolio_gaps", {}),
        "errors": result.get("errors", []),
    }


def create_portfolio_graph() -> StateGraph:
    """Create the portfolio analysis graph.
    
    Structure:
        START -> Portfolio Analyst -> END
    """
    workflow = StateGraph(PortfolioState)
    workflow.add_node("portfolio_analyst", _portfolio_analyst_adapter)
    workflow.add_edge(START, "portfolio_analyst")
    workflow.add_edge("portfolio_analyst", END)
    return workflow.compile()


def _run_portfolio_analysis(
    published_quickstarts: list[dict],
    force: bool = False,
) -> tuple[PortfolioAnalysis | None, dict]:
    """Run portfolio analysis in its own traced LangGraph, with caching.
    
    Returns:
        Tuple of (PortfolioAnalysis, portfolio_gaps dict)
    """
    from agents.portfolio import dict_to_portfolio_analysis, portfolio_analysis_to_dict
    from analysis_store import get_cached_portfolio, cache_portfolio
    
    # Check cache first
    if not force:
        cached = get_cached_portfolio()
        if cached:
            logger.debug("Using cached portfolio analysis")
            portfolio = dict_to_portfolio_analysis(cached.get("portfolio", {}))
            gaps = cached.get("gaps", {})
            return portfolio, gaps
    
    initial_state: PortfolioState = {
        "published_quickstarts": published_quickstarts,
        "portfolio_gaps": {},
        "errors": [],
    }
    
    config = {}
    langfuse_handler = get_langfuse_handler()
    
    if langfuse_handler and is_langfuse_configured():
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {
            "langfuse_session_id": "portfolio-analysis",
            "langfuse_tags": ["portfolio-analysis"],
        }
        logger.debug("Langfuse tracing enabled for portfolio analysis")
    
    try:
        graph = create_portfolio_graph()
        result = graph.invoke(initial_state, config=config)
        
        portfolio = result.get("portfolio_analysis")
        gaps = result.get("portfolio_gaps", {})
        
        # Cache the result
        if portfolio:
            cache_portfolio(portfolio_analysis_to_dict(portfolio), gaps)
        
        logger.debug("Portfolio analysis complete")
        return portfolio, gaps
        
    except Exception as e:
        logger.error("Portfolio analysis graph failed: %s", e)
        return None, {}
    finally:
        flush_langfuse()


# Default max concurrent issue analyses.
# Each issue spawns ~3 parallel LLM calls internally, so 6 concurrent
# issues means ~18 simultaneous API requests.
DEFAULT_MAX_WORKERS = 6


def _analyze_single_issue(
    issue: dict,
    published_quickstarts: list[dict],
    org_repos: list[dict],
    portfolio_gaps: dict,
    include_personas: bool,
    include_platform: bool,
    force_reanalyze: bool,
    on_issue_start: callable,
    on_issue_complete: callable,
    on_issue_cached: callable,
) -> IssueResult:
    """Analyze a single issue. Thread-safe; called from the pool."""
    from agents import final_analysis_to_dict, dict_to_final_analysis
    from analysis_store import get_cached_analysis, cache_analysis

    issue_number = issue.get("number", 0)
    issue_title = issue.get("title", "Untitled")

    # Check cache first
    if not force_reanalyze:
        cached = get_cached_analysis(issue_number)
        if cached:
            logger.debug("Using cached analysis for issue #%s", issue_number)
            if on_issue_cached:
                on_issue_cached(issue_number, issue_title)
            return IssueResult(
                issue_number=issue_number,
                issue_title=issue_title,
                analysis=dict_to_final_analysis(cached.get("analysis", {})),
                analyzed_at=cached.get("analyzed_at", ""),
            )

    if on_issue_start:
        on_issue_start(issue_number, issue_title)

    try:
        analysis = analyze_issue(
            issue=issue,
            published_quickstarts=published_quickstarts,
            org_repos=org_repos,
            portfolio_gaps=portfolio_gaps,
            include_personas=include_personas,
            include_platform=include_platform,
        )

        analyzed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cache_analysis(
            issue_number,
            final_analysis_to_dict(analysis),
            issue_title,
        )

        if on_issue_complete:
            on_issue_complete(issue_number, issue_title)

        return IssueResult(
            issue_number=issue_number,
            issue_title=issue_title,
            analysis=analysis,
            analyzed_at=analyzed_at,
        )

    except Exception as e:
        error_msg = f"Failed to analyze issue #{issue_number}: {str(e)}"
        logger.error(error_msg)
        return IssueResult(
            issue_number=issue_number,
            issue_title=issue_title,
            analysis=FinalAnalysis(),
        )


def generate_report_analysis(
    issues: list[dict],
    published_quickstarts: list[dict],
    org_repos: list[dict],
    include_personas: bool = True,
    include_platform: bool = True,
    force_reanalyze: bool = False,
    skip_portfolio: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    on_issue_start: callable = None,
    on_issue_complete: callable = None,
    on_issue_cached: callable = None,
) -> tuple[PortfolioAnalysis | None, list[IssueResult]]:
    """Run the full report analysis workflow.
    
    Orchestration:
        1. Portfolio analysis graph (single LangGraph invocation)
        2. Per-issue analysis in parallel (thread pool)
    
    Each issue analysis gets its own LangGraph invocation with a clean
    trace session, avoiding nested graph callback conflicts.
    
    Args:
        issues: List of GitHub issues to analyze
        published_quickstarts: Existing quickstarts catalog
        org_repos: Organization repositories
        include_personas: Run persona panel analysis
        include_platform: Run platform specialist analysis
        force_reanalyze: Force re-analysis even if cached
        skip_portfolio: Skip portfolio analysis
        max_workers: Max concurrent issue analyses (default 6)
        on_issue_start: Optional callback(issue_number, issue_title)
        on_issue_complete: Optional callback(issue_number, issue_title)
        on_issue_cached: Optional callback(issue_number, issue_title)
    
    Returns:
        Tuple of (PortfolioAnalysis or None, list of IssueResults)
    """
    # Step 1: Portfolio analysis (if applicable)
    portfolio = None
    portfolio_gaps = {}
    
    if not skip_portfolio:
        portfolio, portfolio_gaps = _run_portfolio_analysis(
            published_quickstarts, force=force_reanalyze,
        )
    
    # Step 2: Analyze issues in parallel
    # Build a map of issue_number -> index to preserve original order
    issue_order = {issue.get("number", i): i for i, issue in enumerate(issues)}
    results: list[IssueResult] = [None] * len(issues)
    
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _analyze_single_issue,
                issue=issue,
                published_quickstarts=published_quickstarts,
                org_repos=org_repos,
                portfolio_gaps=portfolio_gaps,
                include_personas=include_personas,
                include_platform=include_platform,
                force_reanalyze=force_reanalyze,
                on_issue_start=on_issue_start,
                on_issue_complete=on_issue_complete,
                on_issue_cached=on_issue_cached,
            ): issue
            for issue in issues
        }
        
        for future in as_completed(futures):
            issue = futures[future]
            idx = issue_order[issue.get("number", 0)]
            results[idx] = future.result()
    
    return portfolio, results
