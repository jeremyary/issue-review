# This project was developed with assistance from AI tools.
"""Format analysis results for terminal display."""

from agents.state import (
    FinalAnalysis,
    OverlapLevel,
    DevelopmentStage,
    BroadAppeal,
    PlatformFit,
)


def format_preview(analysis: FinalAnalysis, include_status: bool = True) -> str:
    """Format analysis for terminal display with rich markup.
    
    Args:
        analysis: The analysis result to format.
        include_status: Whether to include classification badges.
    """
    lines = []
    
    if include_status:
        # Classification badges
        overlap_colors = {
            OverlapLevel.UNIQUE: "[cyan]UNIQUE[/cyan]",
            OverlapLevel.POSSIBLE_OVERLAP: "[yellow]POSSIBLE OVERLAP[/yellow]",
            OverlapLevel.UNCLEAR: "[dim]UNCLEAR[/dim]",
        }
        
        stage_colors = {
            DevelopmentStage.HAS_CODE: "[green]HAS CODE[/green]",
            DevelopmentStage.DETAILED_PLAN: "[blue]DETAILED PLAN[/blue]",
            DevelopmentStage.DETAILED_CONCEPT: "[cyan]DETAILED CONCEPT[/cyan]",
            DevelopmentStage.CONCEPT_SUMMARY: "[dim]CONCEPT SUMMARY[/dim]",
        }
        
        fit_colors = {
            PlatformFit.EXCELLENT: "[green]EXCELLENT[/green]",
            PlatformFit.GOOD: "[blue]GOOD[/blue]",
            PlatformFit.MODERATE: "[yellow]MODERATE[/yellow]",
            PlatformFit.POOR: "[red]POOR[/red]",
        }
        
        appeal_colors = {
            BroadAppeal.UNIVERSAL: "[green]UNIVERSAL[/green]",
            BroadAppeal.BUSINESS_SPECIFIC: "[blue]BUSINESS SPECIFIC[/blue]",
            BroadAppeal.TECHNICAL_ONLY: "[dim]TECHNICAL ONLY[/dim]",
        }
        
        level_str = overlap_colors.get(analysis.overlap_level, "UNKNOWN")
        stage_str = stage_colors.get(analysis.development_stage, "UNKNOWN")
        fit_str = fit_colors.get(analysis.platform_fit, "UNKNOWN")
        appeal_str = appeal_colors.get(analysis.broad_appeal, "UNKNOWN")
        
        # Priority score with color
        if analysis.priority_score >= 8:
            priority_str = f"[bold green]{analysis.priority_score}/10[/bold green]"
        elif analysis.priority_score >= 5:
            priority_str = f"[blue]{analysis.priority_score}/10[/blue]"
        else:
            priority_str = f"[dim]{analysis.priority_score}/10[/dim]"
        
        lines.extend([
            f"[bold]Suggested Priority:[/bold] {priority_str}",
            f"[bold]Overlap:[/bold] {level_str}  [bold]Stage:[/bold] {stage_str}",
            f"[bold]Platform Fit:[/bold] {fit_str}  [bold]Broad Appeal:[/bold] {appeal_str}",
            "",
        ])
    
    # Coordinator's recommendation
    if analysis.overall_recommendation:
        lines.extend([
            f"[bold]Recommendation:[/bold]",
            f"  {analysis.overall_recommendation}",
            "",
        ])
    
    # Technical summary
    if analysis.technical_summary:
        lines.extend([
            f"[bold]Technical Analysis:[/bold]",
            f"  {analysis.technical_summary}",
            "",
        ])
    
    # Audience analysis
    if analysis.appeal_summary:
        lines.extend([
            f"[bold]Audience Analysis:[/bold]",
            f"  {analysis.appeal_summary}",
            "",
        ])
    
    # Personas breakdown
    if analysis.personas_who_understand or analysis.personas_who_dont:
        if analysis.personas_who_understand:
            lines.append(f"  [green]Resonates with:[/green] {', '.join(analysis.personas_who_understand)}")
        if analysis.personas_who_dont:
            lines.append(f"  [dim]Less relevant for:[/dim] {', '.join(analysis.personas_who_dont)}")
        lines.append("")
    
    # Platform features
    if analysis.features_new or analysis.features_reused:
        lines.append("[bold]Platform Features:[/bold]")
        if analysis.features_new:
            lines.append(f"  [green]New demonstrations:[/green] {', '.join(analysis.features_new[:5])}")
        if analysis.features_reused:
            lines.append(f"  [dim]Seen in published quickstarts:[/dim] {', '.join(analysis.features_reused[:5])}")
        lines.append("")
    
    # Related quickstarts
    if analysis.use_case_overlap:
        lines.append("[bold]Related Quickstarts (Use Case):[/bold]")
        for qs in analysis.use_case_overlap[:3]:
            # Handle both dict and string formats
            if isinstance(qs, dict):
                name = qs.get("name", "Unknown")
                reason = qs.get("reason", "")
                if len(reason) > 70:
                    reason = reason[:70] + "..."
                lines.append(f"  - {name}: {reason}")
            else:
                lines.append(f"  - {qs}")
        lines.append("")
    
    if analysis.similar_stack:
        lines.append("[bold]Related Quickstarts (Technology):[/bold]")
        for qs in analysis.similar_stack[:3]:
            # Handle both dict and string formats
            if isinstance(qs, dict):
                name = qs.get("name", "Unknown")
                reason = qs.get("reason", "")
                if len(reason) > 70:
                    reason = reason[:70] + "..."
                lines.append(f"  - {name}: {reason}")
            else:
                lines.append(f"  - {qs}")
        lines.append("")
    
    # Identified gaps
    if analysis.adjacent_gaps:
        lines.append("[bold]Identified Gaps:[/bold]")
        for gap in analysis.adjacent_gaps[:3]:
            lines.append(f"  - {gap}")
        lines.append("")
    
    return "\n".join(lines)
