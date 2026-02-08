# This project was developed with assistance from AI tools.
"""Shared state definitions for the multi-agent analysis workflow."""

from typing import TypedDict, Annotated
from dataclasses import dataclass, field
from enum import Enum
import operator


class OverlapLevel(Enum):
    """Level of overlap with existing quickstarts."""
    UNIQUE = "unique"
    POSSIBLE_OVERLAP = "possible_overlap"
    UNCLEAR = "unclear"
    
    @classmethod
    def from_string(cls, value: str) -> "OverlapLevel":
        """Parse string to OverlapLevel enum."""
        normalized = value.upper().replace(" ", "_")
        mapping = {
            "UNIQUE": cls.UNIQUE,
            "POSSIBLE_OVERLAP": cls.POSSIBLE_OVERLAP,
            "UNCLEAR": cls.UNCLEAR,
        }
        return mapping.get(normalized, cls.UNCLEAR)


class DevelopmentStage(Enum):
    """Development stage of the proposed quickstart.
    
    Four levels from least to most mature:
    - CONCEPT_SUMMARY: Brief idea, just a few sentences
    - DETAILED_CONCEPT: Expanded explanation but still conceptual
    - DETAILED_PLAN: Specific technologies, architecture, implementation path
    - HAS_CODE: Actual code, repository, or working prototype
    """
    HAS_CODE = "has_code"
    DETAILED_PLAN = "detailed_plan"
    DETAILED_CONCEPT = "detailed_concept"
    CONCEPT_SUMMARY = "concept_summary"
    
    @classmethod
    def from_string(cls, value: str) -> "DevelopmentStage":
        """Parse string to DevelopmentStage enum."""
        normalized = value.upper().replace(" ", "_")
        mapping = {
            "HAS_CODE": cls.HAS_CODE,
            "DETAILED_PLAN": cls.DETAILED_PLAN,
            "DETAILED_CONCEPT": cls.DETAILED_CONCEPT,
            "CONCEPT_SUMMARY": cls.CONCEPT_SUMMARY,
        }
        return mapping.get(normalized, cls.CONCEPT_SUMMARY)


class BroadAppeal(Enum):
    """Broad appeal classification for non-technical audiences."""
    UNIVERSAL = "universal"
    BUSINESS_SPECIFIC = "business_specific"
    TECHNICAL_ONLY = "technical_only"
    
    @classmethod
    def from_string(cls, value: str) -> "BroadAppeal":
        """Parse string to BroadAppeal enum."""
        normalized = value.upper().replace(" ", "_")
        mapping = {
            "UNIVERSAL": cls.UNIVERSAL,
            "BUSINESS_SPECIFIC": cls.BUSINESS_SPECIFIC,
            "TECHNICAL_ONLY": cls.TECHNICAL_ONLY,
        }
        return mapping.get(normalized, cls.TECHNICAL_ONLY)


class PlatformFit(Enum):
    """How well the quickstart fits the OpenShift AI platform."""
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    
    @classmethod
    def from_string(cls, value: str) -> "PlatformFit":
        """Parse string to PlatformFit enum."""
        normalized = value.upper()
        mapping = {
            "EXCELLENT": cls.EXCELLENT,
            "GOOD": cls.GOOD,
            "MODERATE": cls.MODERATE,
            "POOR": cls.POOR,
        }
        return mapping.get(normalized, cls.MODERATE)


@dataclass
class TechnicalAnalysis:
    """Output from the Technical Analyst agent."""
    overlap_level: OverlapLevel = OverlapLevel.UNCLEAR
    development_stage: DevelopmentStage = DevelopmentStage.CONCEPT_SUMMARY
    use_case_overlap: list[dict] = field(default_factory=list)
    similar_stack: list[dict] = field(default_factory=list)
    adjacent_gaps: list[str] = field(default_factory=list)
    clarification_needed: str = ""
    summary: str = ""


@dataclass
class PersonaEvaluation:
    """Single persona's evaluation of the quickstart."""
    persona_id: str = ""
    persona_name: str = ""
    professionally_relevant: bool = False
    relevance: str = "NONE"  # HIGH, MEDIUM, LOW, NONE
    explanation: str = ""


@dataclass
class BroadAppealAnalysis:
    """Aggregated output from the Persona Panel."""
    broad_appeal: BroadAppeal = BroadAppeal.TECHNICAL_ONLY
    personas_who_understand: list[str] = field(default_factory=list)
    personas_who_dont: list[str] = field(default_factory=list)
    evaluations: list[PersonaEvaluation] = field(default_factory=list)
    summary: str = ""


@dataclass
class PlatformAnalysis:
    """Output from the Platform Specialist agent."""
    features_identified: list[dict] = field(default_factory=list)
    features_new: list[str] = field(default_factory=list)
    features_reused: list[str] = field(default_factory=list)
    platform_fit: PlatformFit = PlatformFit.MODERATE
    notes: str = ""


@dataclass
class PortfolioAnalysis:
    """Output from the Portfolio Analyst agent."""
    underserved_industries: list[str] = field(default_factory=list)
    missing_use_cases: list[str] = field(default_factory=list)
    undemonstrated_capabilities: list[str] = field(default_factory=list)
    expected_adjacencies: list[str] = field(default_factory=list)
    summary: str = ""
    notes: str = ""


@dataclass
class FinalAnalysis:
    """Final synthesized analysis from the Coordinator."""
    # From Technical Analyst
    overlap_level: OverlapLevel = OverlapLevel.UNCLEAR
    development_stage: DevelopmentStage = DevelopmentStage.CONCEPT_SUMMARY
    use_case_overlap: list[dict] = field(default_factory=list)
    similar_stack: list[dict] = field(default_factory=list)
    adjacent_gaps: list[str] = field(default_factory=list)
    clarification_needed: str = ""
    technical_summary: str = ""
    
    # From Persona Panel
    broad_appeal: BroadAppeal = BroadAppeal.TECHNICAL_ONLY
    personas_who_understand: list[str] = field(default_factory=list)
    personas_who_dont: list[str] = field(default_factory=list)
    persona_evaluations: list[dict] = field(default_factory=list)  # [{name, relevance, explanation}]
    appeal_summary: str = ""
    
    # From Platform Specialist
    features_identified: list[dict] = field(default_factory=list)
    features_new: list[str] = field(default_factory=list)
    features_reused: list[str] = field(default_factory=list)
    platform_fit: PlatformFit = PlatformFit.MODERATE
    
    # From Coordinator
    overall_recommendation: str = ""
    priority_score: int = 5  # 1-10
    fills_portfolio_gap: list[str] = field(default_factory=list)  # Which gaps this fills
    raw_analysis: str = ""


class AnalysisState(TypedDict, total=False):
    """Shared state for the analysis workflow graph.
    
    This state is passed between all agents in the graph and accumulates
    results from each agent's analysis.
    """
    # Input data
    issue: dict
    published_quickstarts: list[dict]
    org_repos: list[dict]
    feature_catalog: list[dict]
    
    # Portfolio-level analysis (from Portfolio Analyst)
    portfolio_analysis: PortfolioAnalysis | None
    portfolio_gaps: dict  # {industries: [], use_cases: [], capabilities: []}
    
    # Agent outputs (populated as agents complete)
    technical_analysis: TechnicalAnalysis | None
    broad_appeal_analysis: BroadAppealAnalysis | None
    platform_analysis: PlatformAnalysis | None
    
    # Final output
    final_analysis: FinalAnalysis | None
    
    # Error tracking
    errors: Annotated[list[str], operator.add]


def final_analysis_to_dict(analysis: FinalAnalysis) -> dict:
    """Convert a FinalAnalysis to a serializable dictionary."""
    return {
        "overlap_level": analysis.overlap_level.value.upper().replace("_", " "),
        "development_stage": analysis.development_stage.value.upper().replace("_", " "),
        "use_case_overlap": analysis.use_case_overlap,
        "similar_stack": analysis.similar_stack,
        "adjacent_gaps": analysis.adjacent_gaps,
        "clarification_needed": analysis.clarification_needed,
        "summary": analysis.technical_summary,
        "broad_appeal": analysis.broad_appeal.value.upper().replace("_", " "),
        "personas_who_understand": analysis.personas_who_understand,
        "personas_who_dont": analysis.personas_who_dont,
        "persona_evaluations": analysis.persona_evaluations,
        "appeal_summary": analysis.appeal_summary,
        "features_identified": analysis.features_identified,
        "features_new": analysis.features_new,
        "features_reused": analysis.features_reused,
        "platform_fit": analysis.platform_fit.value.upper(),
        "overall_recommendation": analysis.overall_recommendation,
        "priority_score": analysis.priority_score,
        "fills_portfolio_gap": analysis.fills_portfolio_gap,
        "raw_analysis": analysis.raw_analysis,
    }


def dict_to_final_analysis(data: dict) -> FinalAnalysis:
    """Convert a dictionary back to a FinalAnalysis."""
    return FinalAnalysis(
        overlap_level=OverlapLevel.from_string(data.get("overlap_level", "UNCLEAR")),
        development_stage=DevelopmentStage.from_string(data.get("development_stage", "CONCEPT_SUMMARY")),
        use_case_overlap=data.get("use_case_overlap", []),
        similar_stack=data.get("similar_stack", []),
        adjacent_gaps=data.get("adjacent_gaps", []),
        clarification_needed=data.get("clarification_needed", ""),
        technical_summary=data.get("summary", ""),
        broad_appeal=BroadAppeal.from_string(data.get("broad_appeal", "TECHNICAL_ONLY")),
        personas_who_understand=data.get("personas_who_understand", []),
        personas_who_dont=data.get("personas_who_dont", []),
        persona_evaluations=data.get("persona_evaluations", []),
        appeal_summary=data.get("appeal_summary", ""),
        features_identified=data.get("features_identified", []),
        features_new=data.get("features_new", []),
        features_reused=data.get("features_reused", []),
        platform_fit=PlatformFit.from_string(data.get("platform_fit", "MODERATE")),
        overall_recommendation=data.get("overall_recommendation", ""),
        priority_score=data.get("priority_score", 5),
        fills_portfolio_gap=data.get("fills_portfolio_gap", []),
        raw_analysis=data.get("raw_analysis", ""),
    )
