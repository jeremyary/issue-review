# This project was developed with assistance from AI tools.
"""Coordinator agent for synthesizing analysis results."""

import json

from agents.state import (
    AnalysisState,
    FinalAnalysis,
    OverlapLevel,
    DevelopmentStage,
    BroadAppeal,
    PlatformFit,
)
from llm.guardrails import validate_coordinator_summary


def coordinator_node(state: AnalysisState) -> dict:
    """Coordinator agent node for LangGraph.
    
    Synthesizes results from all specialist agents into a final analysis:
    - Technical Analyst: Overlap and development stage
    - Persona Panel: Broad appeal assessment
    - Platform Specialist: OpenShift AI features
    - Portfolio gaps: Check if this issue fills catalog blind spots
    
    LangGraph callback handler automatically traces this node's execution.
    """
    technical = state.get("technical_analysis")
    broad_appeal = state.get("broad_appeal_analysis")
    platform = state.get("platform_analysis")
    portfolio_gaps = state.get("portfolio_gaps", {})
    errors = state.get("errors", [])
    
    # Build final analysis from available agent outputs
    final = FinalAnalysis()
    
    # Incorporate Technical Analyst results
    if technical:
        final.overlap_level = technical.overlap_level
        final.development_stage = technical.development_stage
        final.use_case_overlap = technical.use_case_overlap
        final.similar_stack = technical.similar_stack
        final.adjacent_gaps = technical.adjacent_gaps
        final.clarification_needed = technical.clarification_needed
        final.technical_summary = technical.summary
    
    # Incorporate Persona Panel results
    if broad_appeal:
        final.broad_appeal = broad_appeal.broad_appeal
        final.personas_who_understand = broad_appeal.personas_who_understand
        final.personas_who_dont = broad_appeal.personas_who_dont
        final.persona_evaluations = [
            {
                "name": e.persona_name,
                "relevance": e.relevance,
                "explanation": e.explanation,
            }
            for e in broad_appeal.evaluations
        ]
        final.appeal_summary = broad_appeal.summary
    
    # Incorporate Platform Specialist results
    if platform:
        final.features_identified = platform.features_identified
        final.features_new = platform.features_new
        final.features_reused = platform.features_reused
        final.platform_fit = platform.platform_fit
    
    # Check if this issue fills portfolio gaps
    issue = state.get("issue", {})
    gaps_filled = _detect_portfolio_gaps_filled(issue, final, portfolio_gaps)
    final.fills_portfolio_gap = gaps_filled
    
    # Generate overall recommendation
    final.overall_recommendation = _generate_recommendation(final)
    final.priority_score = _calculate_priority_score(final)
    
    # Build raw analysis JSON for reference
    raw = {
        "technical": {
            "overlap_level": final.overlap_level.value if final.overlap_level else None,
            "development_stage": final.development_stage.value if final.development_stage else None,
            "summary": final.technical_summary,
        },
        "broad_appeal": {
            "level": final.broad_appeal.value if final.broad_appeal else None,
            "personas_understand": final.personas_who_understand,
            "personas_dont": final.personas_who_dont,
        },
        "platform": {
            "fit": final.platform_fit.value if final.platform_fit else None,
            "features_new": final.features_new,
            "features_reused": final.features_reused,
        },
        "coordinator": {
            "priority_score": final.priority_score,
            "recommendation": final.overall_recommendation,
        },
        "errors": errors,
    }
    final.raw_analysis = json.dumps(raw, indent=2)
    
    # Validate the summary with guardrails
    if final.technical_summary:
        guardrail_result = validate_coordinator_summary(final.technical_summary)
        if not guardrail_result.is_safe:
            # Log but don't block - prepend warning to raw analysis
            warning = f"[Guardrail warning: {guardrail_result.reason}]\n\n"
            final.raw_analysis = warning + final.raw_analysis
    
    return {"final_analysis": final}


def _detect_portfolio_gaps_filled(issue: dict, analysis: FinalAnalysis, portfolio_gaps: dict) -> list[str]:
    """Detect which portfolio gaps this issue might fill.
    
    Uses keyword matching against issue title/body and analysis summary
    to identify potential gap coverage.
    """
    if not portfolio_gaps:
        return []
    
    # Build searchable text from issue and analysis
    title = (issue.get("title") or "").lower()
    body = (issue.get("body") or "").lower()
    summary = (analysis.technical_summary or "").lower()
    search_text = f"{title} {body} {summary}"
    
    gaps_filled = []
    
    # Check underserved industries
    industry_keywords = {
        "healthcare": ["healthcare", "medical", "clinical", "patient", "hospital", "diagnostic", "health"],
        "financial services": ["financial", "banking", "fraud", "trading", "credit", "loan", "mortgage", "compliance"],
        "manufacturing": ["manufacturing", "factory", "quality control", "defect", "production", "assembly", "industrial"],
        "retail": ["retail", "inventory", "e-commerce", "shopping", "store", "merchandis"],
        "legal": ["legal", "law", "contract", "court", "litigation", "compliance", "regulatory"],
    }
    
    for industry in portfolio_gaps.get("industries", []):
        industry_lower = industry.lower()
        # Check direct mention or keyword match
        for ind_name, keywords in industry_keywords.items():
            if ind_name in industry_lower:
                if any(kw in search_text for kw in keywords):
                    gaps_filled.append(f"Industry: {ind_name.title()}")
                    break
    
    # Check missing use cases
    use_case_keywords = {
        "document intelligence": ["document", "invoice", "form", "ocr", "pdf", "extraction", "contract analysis"],
        "computer vision": ["computer vision", "image", "video", "visual", "camera", "object detection", "cv"],
        "fraud detection": ["fraud", "anomaly detection", "suspicious", "risk scoring"],
        "predictive maintenance": ["predictive maintenance", "equipment failure", "sensor", "iot", "time series"],
        "customer service": ["customer service", "call center", "chatbot", "support ticket", "helpdesk"],
    }
    
    for use_case in portfolio_gaps.get("use_cases", []):
        use_case_lower = use_case.lower()
        for uc_name, keywords in use_case_keywords.items():
            if uc_name in use_case_lower:
                if any(kw in search_text for kw in keywords):
                    gaps_filled.append(f"Use Case: {uc_name.title()}")
                    break
    
    # Check undemonstrated capabilities
    capability_keywords = {
        "computer vision": ["computer vision", "image classification", "object detection", "visual"],
        "fine-tuning": ["fine-tuning", "fine tuning", "model customization", "domain adaptation"],
        "speech": ["speech", "audio", "voice", "transcription", "stt", "tts"],
        "batch processing": ["batch", "bulk", "large-scale", "offline processing"],
    }
    
    for capability in portfolio_gaps.get("capabilities", []):
        cap_lower = capability.lower()
        for cap_name, keywords in capability_keywords.items():
            if cap_name in cap_lower:
                if any(kw in search_text for kw in keywords):
                    gaps_filled.append(f"Capability: {cap_name.title()}")
                    break
    
    # Deduplicate
    return list(dict.fromkeys(gaps_filled))


def _generate_recommendation(analysis: FinalAnalysis) -> str:
    """Generate an overall recommendation based on the analysis."""
    parts = []
    
    # Overlap assessment
    if analysis.overlap_level == OverlapLevel.UNIQUE:
        parts.append("Unique use case - no overlap with existing quickstarts.")
    elif analysis.overlap_level == OverlapLevel.POSSIBLE_OVERLAP:
        overlaps = len(analysis.use_case_overlap)
        parts.append(f"Possible overlap with {overlaps} existing quickstart(s) - review recommended.")
    else:
        parts.append("Use case needs clarification before overlap can be assessed.")
    
    # Development stage
    if analysis.development_stage == DevelopmentStage.HAS_CODE:
        parts.append("Contributor has existing code/prototype.")
    elif analysis.development_stage == DevelopmentStage.DETAILED_PLAN:
        parts.append("Detailed implementation plan ready for development.")
    elif analysis.development_stage == DevelopmentStage.DETAILED_CONCEPT:
        parts.append("Well-described concept - needs some planning before implementation.")
    else:  # CONCEPT_SUMMARY
        parts.append("Brief concept summary - needs follow-up for details.")
    
    # Broad appeal
    if analysis.appeal_summary:
        parts.append(f"Appeal: {analysis.broad_appeal.value.replace('_', ' ').title()}.")
    
    # Platform features
    if analysis.features_new:
        parts.append(f"Would demonstrate {len(analysis.features_new)} new platform feature(s).")
    
    # Portfolio gaps
    if analysis.fills_portfolio_gap:
        parts.append(f"Fills catalog gap: {', '.join(analysis.fills_portfolio_gap[:2])}.")
    
    return " ".join(parts)


def _calculate_priority_score(analysis: FinalAnalysis) -> int:
    """Calculate a priority score (1-10) based on the analysis.
    
    Higher scores indicate more valuable contributions:
    - Unique use cases score higher
    - More developed proposals score higher
    - Broader appeal scores higher
    - New platform features score higher
    - Filling portfolio gaps scores higher
    """
    score = 4  # Start at neutral
    
    # Overlap factor
    if analysis.overlap_level == OverlapLevel.UNIQUE:
        score += 1
    elif analysis.overlap_level == OverlapLevel.UNCLEAR:
        score -= 1
    # POSSIBLE_OVERLAP stays neutral
    
    # Development stage factor (4 levels: +2, +1, +0, -3)
    if analysis.development_stage == DevelopmentStage.HAS_CODE:
        score += 2
    elif analysis.development_stage == DevelopmentStage.DETAILED_PLAN:
        score += 1
    elif analysis.development_stage == DevelopmentStage.DETAILED_CONCEPT:
        pass  # Neutral
    else:  # CONCEPT_SUMMARY
        score -= 3
    
    # Broad appeal factor
    if analysis.broad_appeal == BroadAppeal.UNIVERSAL:
        score += 1
    elif analysis.broad_appeal == BroadAppeal.TECHNICAL_ONLY:
        score -= 1
    
    # Platform features factor
    if analysis.features_new:
        score += min(len(analysis.features_new), 2)  # Cap at +2
    
    # Portfolio gap factor - filling gaps is valuable
    if analysis.fills_portfolio_gap:
        score += min(len(analysis.fills_portfolio_gap), 2)  # Cap at +2
    
    # Clamp to 1-10
    return max(1, min(10, score))
