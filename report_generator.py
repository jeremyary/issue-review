# This project was developed with assistance from AI tools.
"""PDF report generation for issue analyses."""

import os
import re
from datetime import datetime
from typing import Optional

from fpdf import FPDF

from agents import strip_issue_prefix, PortfolioAnalysis
from config import GITHUB_ORG, GITHUB_REPO
from data import load_features, get_all_demonstrated_features


# Feature ID to display name mapping
FEATURE_DISPLAY_NAMES = {
    # Model Serving
    "kserve": "KServe",
    "modelmesh": "ModelMesh",
    "vllm": "vLLM",
    "tgis": "TGIS",
    "caikit": "Caikit",
    "openvino": "OpenVINO",
    "nvidia_nim": "NVIDIA NIM",
    "custom_runtime": "Custom Runtime",
    "cpu_inference": "CPU Inference",
    # Model Training
    "training": "Model Training",
    "fine_tuning": "Fine-tuning",
    "instructlab": "InstructLab",
    # ML Pipelines
    "pipelines": "Data Science Pipelines",
    "feature_store": "Feature Store (Feast)",
    # Model Management
    "model_registry": "Model Registry",
    "lm_eval": "LM-Eval",
    # Governance & Trust
    "guardrails": "Guardrails",
    "trustyai": "TrustyAI",
    # Observability
    "opentelemetry": "OpenTelemetry",
    "prometheus": "Prometheus",
    # Data & Storage
    "vector_db": "Vector DB",
    "object_storage": "Object Storage",
    # Agent Frameworks
    "llamastack": "LlamaStack",
    "langgraph": "LangGraph",
    "mcp": "MCP",
    # RAG Components
    "rag": "RAG",
    "embeddings": "Embeddings",
    # Development Environment
    "workbench": "Workbench",
    "ds_projects": "DS Projects",
    # Infrastructure
    "distributed_workloads": "Distributed Workloads",
    "accelerator_profiles": "GPU / Accelerators",
}


def _get_feature_display_name(feature_id: str) -> str:
    """Get display name for a feature ID."""
    return FEATURE_DISPLAY_NAMES.get(feature_id, feature_id)


def sanitize_text(text: str) -> str:
    """Sanitize text for PDF output by replacing Unicode characters with ASCII equivalents."""
    if not text:
        return text
    
    replacements = {
        '\u2011': '-',  # non-breaking hyphen
        '\u2010': '-',  # hyphen
        '\u2012': '-',  # figure dash
        '\u2013': '-',  # en dash
        '\u2014': '-',  # em dash
        '\u2015': '-',  # horizontal bar
        '\u2018': "'",  # left single quote
        '\u2019': "'",  # right single quote
        '\u201c': '"',  # left double quote
        '\u201d': '"',  # right double quote
        '\u2026': '...',  # ellipsis
        '\u00a0': ' ',  # non-breaking space
        '\u200b': '',   # zero-width space
        '\u2022': '*',  # bullet
        '\u2023': '>',  # triangular bullet
        '\u2043': '-',  # hyphen bullet
        '\u00b7': '*',  # middle dot
    }
    
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    
    # Remove any remaining non-latin1 characters
    return text.encode('latin-1', errors='replace').decode('latin-1')


class ReportPDF(FPDF):
    """Custom PDF class for the analysis report."""
    
    def header(self):
        # Only show the report title on the first page
        if self.page_no() == 1:
            self.set_font("Helvetica", "B", 14)
            self.cell(0, 10, "Quickstart Suggestion Analysis Report", align="C", new_x="LMARGIN", new_y="NEXT")
            self.ln(3)
    
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _render_label_value(pdf, label: str, value: str, color: tuple = None):
    """Render a label: value pair, with optional color for the value."""
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(pdf.get_string_width(f"{label}: "), 5, f"{label}: ")
    if color:
        pdf.set_text_color(*color)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def _render_section_header(pdf, title: str):
    """Render a section header."""
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)


def _render_priority_summary(pdf, issues: list[dict], analyses: dict):
    """Render priority counts at the top of the report."""
    # Count priorities
    high_priority = 0
    medium_priority = 0
    low_priority = 0
    
    for issue in issues:
        issue_num = str(issue.get("number"))
        if issue_num in analyses:
            analysis_data = analyses[issue_num].get("analysis", {})
            score = analysis_data.get("priority_score", 5)
            if score >= 8:
                high_priority += 1
            elif score >= 5:
                medium_priority += 1
            else:
                low_priority += 1
    
    # Priority breakdown with colors
    pdf.set_font("Helvetica", "", 9)
    
    pdf.set_text_color(40, 167, 69)
    pdf.cell(pdf.get_string_width(f"{high_priority} high"), 5, f"{high_priority} high")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(pdf.get_string_width("  |  "), 5, "  |  ")
    
    pdf.set_text_color(0, 123, 255)
    pdf.cell(pdf.get_string_width(f"{medium_priority} medium"), 5, f"{medium_priority} medium")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(pdf.get_string_width("  |  "), 5, "  |  ")
    
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 5, f"{low_priority} low", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    
    pdf.ln(5)


def _render_clarification(pdf, text: str):
    """Render the clarification/further info section with consistent formatting.
    
    Handles LLM output that may or may not use '- ' prefixes on list items.
    Normalizes the output so category headers are bold and items are bulleted.
    """
    # Known category headers (case-insensitive match)
    category_headers = [
        "use case details",
        "technical details",
    ]
    
    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check if this is a category header
        stripped_lower = stripped.rstrip(":").lower()
        is_header = any(h in stripped_lower for h in category_headers)
        
        if is_header:
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 5, sanitize_text(stripped), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 9)
        elif stripped.startswith("- "):
            pdf.multi_cell(0, 5, sanitize_text(f"  * {stripped[2:]}"), new_x="LMARGIN", new_y="NEXT")
        elif stripped.startswith("* "):
            pdf.multi_cell(0, 5, sanitize_text(f"  {stripped}"), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5, sanitize_text(stripped), new_x="LMARGIN", new_y="NEXT")


def _render_portfolio_analysis(pdf, portfolio: PortfolioAnalysis):
    """Render the portfolio-level blind spots analysis."""
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 6, "Portfolio Blind Spots Analysis (based SOLELY on PUBLISHED quickstarts)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    
    # Executive summary
    if portfolio.summary:
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, sanitize_text(portfolio.summary), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    
    # Platform features not yet demonstrated by any published quickstart
    features = load_features()
    demonstrated = get_all_demonstrated_features()
    not_demonstrated = [
        f for f in features if f["id"] not in demonstrated
    ]
    if not_demonstrated:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Platform Features Not Yet Demonstrated", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        feature_labels = [
            _get_feature_display_name(f["id"]) for f in not_demonstrated
        ]
        pdf.multi_cell(0, 5, f"  {', '.join(feature_labels)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    # Underserved Industries
    if portfolio.underserved_industries:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Underserved Industries", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        for item in portfolio.underserved_industries[:5]:
            pdf.multi_cell(0, 5, f"  * {sanitize_text(item)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    # Missing Use Cases
    if portfolio.missing_use_cases:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Missing Use Cases", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        for item in portfolio.missing_use_cases[:5]:
            pdf.multi_cell(0, 5, f"  * {sanitize_text(item)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    # Undemonstrated Capabilities
    if portfolio.undemonstrated_capabilities:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Undemonstrated Capabilities", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        for item in portfolio.undemonstrated_capabilities[:5]:
            pdf.multi_cell(0, 5, f"  * {sanitize_text(item)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    # Expected Adjacencies
    if portfolio.expected_adjacencies:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Expected Adjacent Quickstarts", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        for item in portfolio.expected_adjacencies[:4]:
            pdf.multi_cell(0, 5, f"  * {sanitize_text(item)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    # Strategic gaps / additional notes
    if portfolio.notes:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 5, "Strategic Gaps", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        # Parse numbered items like "(1) ..., (2) ..." into a list
        notes_text = portfolio.notes
        # Strip leading label if present
        if notes_text.lower().startswith("strategic gaps:"):
            notes_text = notes_text[len("strategic gaps:"):].strip()
        items = re.split(r'\(\d+\)\s*', notes_text)
        items = [item.strip().rstrip(',').strip() for item in items if item.strip()]
        if items:
            for item in items:
                pdf.multi_cell(0, 5, f"  * {sanitize_text(item)}", new_x="LMARGIN", new_y="NEXT")
        else:
            # Fallback if not in numbered format
            pdf.multi_cell(0, 5, f"  * {sanitize_text(notes_text)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    
    pdf.ln(3)
    pdf.set_draw_color(0, 51, 102)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(220, 220, 220)
    pdf.ln(8)


def generate_pdf_report(
    issues: list[dict],
    analyses: dict,
    output_path: Optional[str] = None,
    portfolio_analysis: Optional[PortfolioAnalysis] = None,
) -> str:
    """
    Generate a PDF report of all issue analyses.
    
    Args:
        issues: List of issue dictionaries
        analyses: Dict mapping issue number (str) to analysis data
        output_path: Optional output path, defaults to reports/report_TIMESTAMP.pdf
        portfolio_analysis: Optional portfolio-level blind spots analysis
    
    Returns:
        Path to the generated PDF file
    """
    if output_path is None:
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(reports_dir, f"analysis_report_{timestamp}.pdf")
    
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Priority counts
    _render_priority_summary(pdf, issues, analyses)
    
    # Portfolio-level blind spots analysis at the top (if provided)
    if portfolio_analysis:
        _render_portfolio_analysis(pdf, portfolio_analysis)
    
    for issue in issues:
        issue_num = str(issue.get("number"))
        title = sanitize_text(strip_issue_prefix(issue.get("title", "Untitled")))
        user = sanitize_text(issue.get("user", "Unknown"))
        issue_url = issue.get("html_url", f"https://github.com/{GITHUB_ORG}/{GITHUB_REPO}/issues/{issue_num}")
        
        # Start new page if not enough room (estimate ~120px per issue minimum)
        if pdf.get_y() > 180:
            pdf.add_page()
        
        # Issue header
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0, 51, 102)
        issue_header = f"Issue #{issue_num}: {title}"
        if len(issue_header) > 85:
            issue_header = issue_header[:85] + "..."
        pdf.multi_cell(0, 6, issue_header, new_x="LMARGIN", new_y="NEXT", link=issue_url)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, f"Submitted by: {user}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        if issue_num in analyses:
            analysis_data = analyses[issue_num].get("analysis", {})
            analyzed_at = analyses[issue_num].get("analyzed_at", "")
            
            # Quick summary metrics
            priority_score = analysis_data.get("priority_score", 5)
            overlap_level = analysis_data.get("overlap_level", "UNCLEAR").replace("_", " ").title()
            dev_stage = analysis_data.get("development_stage", "CONCEPT").replace("_", " ").title()
            platform_fit = analysis_data.get("platform_fit", "MODERATE").replace("_", " ").title()
            broad_appeal = analysis_data.get("broad_appeal", "TECHNICAL ONLY").replace("_", " ").title()
            
            if priority_score >= 8:
                priority_label = "High"
            elif priority_score >= 5:
                priority_label = "Medium"
            else:
                priority_label = "Low"
            _render_label_value(pdf, "Suggested Priority", priority_label)
            _render_label_value(pdf, "Overlap", overlap_level)
            _render_label_value(pdf, "Stage", dev_stage)
            _render_label_value(pdf, "Platform Fit", platform_fit)
            _render_label_value(pdf, "Broad Appeal", broad_appeal)
            
            # Summary (what the issue proposes)
            summary = sanitize_text(analysis_data.get("summary", ""))
            if summary:
                _render_section_header(pdf, "Summary")
                pdf.multi_cell(0, 5, summary, new_x="LMARGIN", new_y="NEXT")
            
            # What's Needed (clarification or details to advance stage)
            clarification = analysis_data.get("clarification_needed", "")
            if clarification:
                _render_section_header(pdf, "Further Info")
                _render_clarification(pdf, clarification)
            
            # Audience Analysis (from Persona Panel)
            appeal_summary = sanitize_text(analysis_data.get("appeal_summary", ""))
            persona_evals = analysis_data.get("persona_evaluations", [])
            
            if appeal_summary or persona_evals:
                _render_section_header(pdf, "Audience Analysis")
                if appeal_summary:
                    pdf.multi_cell(0, 5, appeal_summary, new_x="LMARGIN", new_y="NEXT")
                
                # Show individual persona evaluations - colored label, black explanation
                if persona_evals:
                    pdf.ln(2)
                    for pe in persona_evals:
                        name = sanitize_text(pe.get("name", "Unknown"))
                        relevance = pe.get("relevance", "NONE")
                        explanation = sanitize_text(pe.get("explanation", ""))
                        
                        # Color code label by relevance
                        if relevance in ("HIGH", "MEDIUM"):
                            pdf.set_text_color(40, 167, 69)  # green
                            symbol = "+"
                        else:
                            pdf.set_text_color(128, 128, 128)  # gray
                            symbol = "-"
                        
                        # Use write() for inline flow so text wraps naturally
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.write(5, f"{symbol} {name}: ")
                        
                        # Explanation in black, continues inline
                        pdf.set_text_color(0, 0, 0)
                        pdf.set_font("Helvetica", "", 9)
                        if explanation:
                            pdf.write(5, explanation)
                        pdf.ln(7)  # Space before next persona
            
            # Platform Features (from Platform Specialist)
            features_new = analysis_data.get("features_new", [])
            features_reused = analysis_data.get("features_reused", [])
            if features_new or features_reused:
                _render_section_header(pdf, "Platform Features")
                if features_new:
                    display_names = [_get_feature_display_name(f) for f in features_new[:8]]
                    pdf.multi_cell(0, 5, f"New to quickstarts: {', '.join(display_names)}", new_x="LMARGIN", new_y="NEXT")
                if features_reused:
                    display_names = [_get_feature_display_name(f) for f in features_reused[:8]]
                    pdf.multi_cell(0, 5, f"Previously demonstrated: {', '.join(display_names)}", new_x="LMARGIN", new_y="NEXT")
            
            # Use Case Overlap
            use_case_overlap = analysis_data.get("use_case_overlap", [])
            if use_case_overlap:
                _render_section_header(pdf, "Use Case Similarities")
                for qs in use_case_overlap[:3]:
                    # Handle both string format and dict format
                    if isinstance(qs, str):
                        name = sanitize_text(qs)
                        reason = ""
                    else:
                        name = sanitize_text(qs.get("name", "Unknown"))
                        reason = sanitize_text(qs.get("reason", ""))
                    
                    if reason:
                        pdf.multi_cell(0, 5, f"  * {name}: {reason}", new_x="LMARGIN", new_y="NEXT")
                    else:
                        pdf.multi_cell(0, 5, f"  * {name}", new_x="LMARGIN", new_y="NEXT")
            
            # Similar Stack
            similar_stack = analysis_data.get("similar_stack", [])
            if similar_stack:
                _render_section_header(pdf, "Tech/Stack Similarities")
                for qs in similar_stack[:3]:
                    # Handle both string format and dict format
                    if isinstance(qs, str):
                        name = sanitize_text(qs)
                        reason = ""
                    else:
                        name = sanitize_text(qs.get("name", "Unknown"))
                        reason = sanitize_text(qs.get("reason", ""))
                    
                    if reason:
                        pdf.multi_cell(0, 5, f"  * {name}: {reason}", new_x="LMARGIN", new_y="NEXT")
                    else:
                        pdf.multi_cell(0, 5, f"  * {name}", new_x="LMARGIN", new_y="NEXT")
            
            # Portfolio catalog gaps filled
            fills_gaps = analysis_data.get("fills_portfolio_gap", [])
            if fills_gaps:
                _render_section_header(pdf, "Fills Catalog Gaps")
                # Group by category (e.g. "Industry", "Use Case", "Capability")
                grouped = {}
                for gap in fills_gaps:
                    if ": " in gap:
                        cat, val = gap.split(": ", 1)
                        grouped.setdefault(cat, []).append(val)
                    else:
                        grouped.setdefault("Other", []).append(gap)
                for cat, values in grouped.items():
                    pdf.multi_cell(0, 5, sanitize_text(f"  * {cat}: {', '.join(values)}"), new_x="LMARGIN", new_y="NEXT")
            
            # Adjacent Gaps
            adjacent_gaps = analysis_data.get("adjacent_gaps", [])
            if adjacent_gaps:
                _render_section_header(pdf, "Identified Gaps")
                for gap in adjacent_gaps[:3]:
                    pdf.multi_cell(0, 5, f"  * {sanitize_text(gap)}", new_x="LMARGIN", new_y="NEXT")
            
            if analyzed_at:
                pdf.ln(2)
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(128, 128, 128)
                pdf.cell(0, 4, f"Analyzed: {analyzed_at[:19].replace('T', ' ')}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(128, 128, 128)
            pdf.cell(0, 6, "Not yet analyzed", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        
        pdf.ln(5)
        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
    
    pdf.output(output_path)
    return output_path
