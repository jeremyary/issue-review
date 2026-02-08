# This project was developed with assistance from AI tools.
"""Multi-agent analysis system using LangGraph."""

from agents.state import (
    AnalysisState,
    FinalAnalysis,
    TechnicalAnalysis,
    BroadAppealAnalysis,
    PlatformAnalysis,
    PortfolioAnalysis,
    OverlapLevel,
    DevelopmentStage,
    BroadAppeal,
    PlatformFit,
    final_analysis_to_dict,
    dict_to_final_analysis,
)
from agents.graph import create_analysis_graph, analyze_issue
from agents.technical import strip_issue_prefix
from agents.portfolio import (
    portfolio_analyst_node,
    portfolio_analysis_to_dict,
    dict_to_portfolio_analysis,
)
from agents.report_graph import (
    IssueResult,
    generate_report_analysis,
)

__all__ = [
    # State types
    "AnalysisState",
    "FinalAnalysis",
    "TechnicalAnalysis",
    "BroadAppealAnalysis",
    "PlatformAnalysis",
    "PortfolioAnalysis",
    "IssueResult",
    # Enums
    "OverlapLevel",
    "DevelopmentStage",
    "BroadAppeal",
    "PlatformFit",
    # Conversion functions
    "final_analysis_to_dict",
    "dict_to_final_analysis",
    "portfolio_analysis_to_dict",
    "dict_to_portfolio_analysis",
    # Utilities
    "strip_issue_prefix",
    # Issue analysis graph
    "create_analysis_graph",
    "analyze_issue",
    # Report analysis workflow
    "generate_report_analysis",
    "portfolio_analyst_node",
]
