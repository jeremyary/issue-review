#!/usr/bin/env python3
# This project was developed with assistance from AI tools.
"""Main CLI entry point for the issue review tool."""

import argparse
import os
import sys
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from config import LLM_BASE_URL, LLM_MODEL, GITHUB_TOKEN
from data_sources import (
    fetch_quickstart_issues,
    fetch_org_repositories,
    get_published_quickstarts,
    get_issue_by_number,
)
from agents import (
    strip_issue_prefix,
    final_analysis_to_dict,
    dict_to_final_analysis,
    generate_report_analysis,
)
from analysis_store import (
    get_cached_analysis,
    get_all_cached_analyses,
    clear_analysis_store,
)
from report_generator import generate_pdf_report
from comment_generator import format_preview

console = Console()


def check_configuration() -> bool:
    """Check that required configuration is present."""
    errors = []
    
    if not GITHUB_TOKEN:
        errors.append("GITHUB_TOKEN is not set")
    
    if not LLM_BASE_URL:
        errors.append("LLM_BASE_URL is not set")
    
    if errors:
        console.print("[bold red]Configuration Error:[/bold red]")
        for error in errors:
            console.print(f"  - {error}")
        console.print("\nPlease set these environment variables in your .env file.")
        return False
    
    return True


def display_analysis_summary(issues: list[dict], analyses: dict):
    """Display a summary table of all analyzed issues."""
    table = Table(title="Analysis Summary")
    table.add_column("#", style="cyan", width=6)
    table.add_column("Title", style="white", max_width=48)
    table.add_column("Overlap", style="yellow", width=18)
    table.add_column("Stage", style="blue", width=17)
    
    for issue in issues:
        issue_num = str(issue.get("number", "?"))
        title = strip_issue_prefix(issue.get("title", "Untitled"))
        if len(title) > 47:
            title = title[:47] + "..."
        
        if issue_num in analyses:
            analysis = analyses[issue_num].get("analysis", {})
            overlap = analysis.get("overlap_level", "?").upper().replace("_", " ")
            stage = analysis.get("development_stage", "?").upper().replace("_", " ")
        else:
            overlap = "Not analyzed"
            stage = "-"
        
        table.add_row(issue_num, title, overlap, stage)
    
    console.print()
    console.print(table)


def cmd_analyze(args):
    """Analyze issues and generate reports."""
    if not check_configuration():
        sys.exit(1)
    
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Quickstart Issue Review Tool[/bold cyan]\n"
        f"[dim]Model: {LLM_MODEL} @ {LLM_BASE_URL}[/dim]",
        border_style="cyan",
    ))
    console.print()
    
    # Auto-sync catalog if stale (unless --no-cache is used)
    if not args.no_cache:
        from indexer import ensure_catalog_fresh
        ensure_catalog_fresh(quiet=False)
    
    # Load supporting data
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading quickstarts catalog...", total=None)
        published_quickstarts = get_published_quickstarts()
        progress.update(task, description=f"Loaded {len(published_quickstarts)} quickstarts")
        progress.remove_task(task)
        
        task = progress.add_task("Loading organization repositories...", total=None)
        org_repos = fetch_org_repositories(bypass_cache=args.no_cache)
        progress.update(task, description=f"Loaded {len(org_repos)} repositories")
        progress.remove_task(task)
        
        # Get issues to analyze
        if args.issue:
            task = progress.add_task(f"Fetching issue #{args.issue}...", total=None)
            issue = get_issue_by_number(args.issue, bypass_cache=args.no_cache)
            progress.remove_task(task)
            
            if not issue:
                console.print(f"[red]Error:[/red] Could not find issue #{args.issue}")
                sys.exit(1)
            issues = [issue]
        else:
            task = progress.add_task("Fetching quickstart suggestions...", total=None)
            issues = fetch_quickstart_issues(bypass_cache=args.no_cache)
            progress.remove_task(task)
    
    if not issues:
        console.print("[yellow]No quickstart suggestion issues found.[/yellow]")
        sys.exit(0)
    
    issues.sort(key=lambda x: x.get("created_at", ""))
    console.print(f"Found [cyan]{len(issues)}[/cyan] issue(s) to process")
    console.print()
    
    # Determine if we should run portfolio analysis
    skip_portfolio = args.issue or len(issues) <= 1 or getattr(args, 'no_portfolio', False)
    
    # Use the report analysis workflow
    if not skip_portfolio:
        console.print("[bold]Running analysis workflow...[/bold]")
        console.print("[dim]Portfolio analysis will run first to inform priority scoring[/dim]")
    else:
        console.print("[bold]Analyzing issues...[/bold]")
    
    portfolio_analysis, issue_results = generate_report_analysis(
        issues=issues,
        published_quickstarts=published_quickstarts,
        org_repos=org_repos,
        force_reanalyze=args.reanalyze,
        skip_portfolio=skip_portfolio,
        on_issue_start=lambda num, title: console.print(f"  Analyzing issue #{num}..."),
        on_issue_complete=lambda num, title: None,
        on_issue_cached=lambda num, title: console.print(f"  [dim]Using cached analysis for #{num}[/dim]"),
    )
    
    # Convert results to the format expected by display_analysis_summary
    analyses = {}
    for result in issue_results:
        issue_num = str(result.issue_number)
        analyses[issue_num] = {
            "analysis": final_analysis_to_dict(result.analysis),
            "analyzed_at": result.analyzed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    if portfolio_analysis:
        console.print("[dim]Portfolio and issue analysis complete[/dim]")
    else:
        console.print("[dim]Issue analysis complete[/dim]")
    
    # Display summary
    display_analysis_summary(issues, analyses)
    
    # Show detailed analysis for single issue
    if args.issue and len(issues) == 1:
        issue_num = str(issues[0].get("number"))
        if issue_num in analyses:
            analysis_dict = analyses[issue_num].get("analysis", {})
            analysis = dict_to_final_analysis(analysis_dict)
            console.print()
            console.print(Panel(
                format_preview(analysis, include_status=False),
                title=f"[bold]Issue #{issue_num} Analysis Details[/bold]",
                border_style="blue",
            ))
    
    # Generate report if requested
    if args.report or args.output:
        console.print()
        
        # Determine output path
        if args.output:
            output_path = args.output
        else:
            # Default to reports directory
            reports_dir = os.path.join(os.path.dirname(__file__), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if args.issue:
                output_path = os.path.join(reports_dir, f"issue_{args.issue}_report_{timestamp}.pdf")
            else:
                output_path = os.path.join(reports_dir, f"issues_report_{timestamp}.pdf")
        
        # Portfolio analysis was already run earlier (if applicable)
        
        console.print(f"Generating report: [cyan]{output_path}[/cyan]")
        
        generate_pdf_report(
            issues=issues,
            analyses=analyses,
            output_path=output_path,
            portfolio_analysis=portfolio_analysis,
        )
        
        console.print(f"[green]Report saved:[/green] {output_path}")


def cmd_list(args):
    """List issues with their analysis status."""
    if not check_configuration():
        sys.exit(1)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching issues...", total=None)
        issues = fetch_quickstart_issues(bypass_cache=args.no_cache)
        progress.remove_task(task)
    
    if not issues:
        console.print("[yellow]No quickstart suggestion issues found.[/yellow]")
        return
    
    issues.sort(key=lambda x: x.get("created_at", ""))
    
    # Get cached analyses
    cached_analyses = get_all_cached_analyses()
    
    table = Table(title="Quickstart Suggestion Issues")
    table.add_column("#", style="cyan", width=6)
    table.add_column("Title", max_width=55)
    table.add_column("Author", style="dim", width=15)
    table.add_column("Analyzed", style="green", width=10)
    
    for issue in issues:
        issue_num = str(issue.get("number", "?"))
        title = strip_issue_prefix(issue.get("title", "Untitled"))
        if len(title) > 52:
            title = title[:52] + "..."
        author = issue.get("user", "Unknown")
        analyzed = "Yes" if issue_num in cached_analyses else "No"
        
        table.add_row(issue_num, title, author, analyzed)
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(issues)} issues[/dim]")


def cmd_show(args):
    """Show detailed analysis for a specific issue."""
    if not check_configuration():
        sys.exit(1)
    
    cached = get_cached_analysis(args.issue)
    
    if not cached:
        console.print(f"[yellow]No cached analysis for issue #{args.issue}[/yellow]")
        console.print(f"Run [cyan]issue-review analyze --issue {args.issue}[/cyan] first.")
        return
    
    analysis_dict = cached.get("analysis", {})
    analysis = dict_to_final_analysis(analysis_dict)
    
    console.print()
    console.print(Panel(
        format_preview(analysis),
        title=f"[bold]Issue #{args.issue} Analysis[/bold]",
        border_style="blue",
    ))
    
    if cached.get("analyzed_at"):
        console.print(f"[dim]Analyzed: {cached.get('analyzed_at')}[/dim]")


def cmd_clear_cache(args):
    """Clear the analysis cache."""
    clear_analysis_store()
    console.print("[green]Analysis cache cleared.[/green]")


def cmd_sync(args):
    """Sync the quickstart catalog."""
    from indexer import sync_catalog, check_catalog_freshness
    
    is_fresh, age_days = check_catalog_freshness()
    
    if args.status:
        # Just show status
        if age_days is None:
            console.print("[yellow]Catalog has never been synced[/yellow]")
        elif is_fresh:
            console.print(f"[green]Catalog is fresh ({age_days} days old)[/green]")
        else:
            console.print(f"[yellow]Catalog is stale ({age_days} days old)[/yellow]")
        return
    
    if not args.force and is_fresh:
        console.print(f"[dim]Catalog is fresh ({age_days} days old)[/dim]")
        console.print("Use [cyan]--force[/cyan] to sync anyway")
        return
    
    success = sync_catalog(quiet=args.quiet)
    
    if not success:
        sys.exit(1)


def cmd_index(args):
    """Index quickstart content for RAG search."""
    from data import get_published_quickstarts
    from indexer import clone_or_pull_repo, index_quickstart, REPOS_DIR
    
    quickstarts = get_published_quickstarts()
    
    if args.quickstart:
        # Filter to specific quickstart
        quickstarts = [qs for qs in quickstarts if qs.get("id") == args.quickstart or qs.get("repo") == args.quickstart]
        if not quickstarts:
            console.print(f"[red]Quickstart not found: {args.quickstart}[/red]")
            sys.exit(1)
    
    console.print(f"[blue]Indexing {len(quickstarts)} quickstart(s)...[/blue]")
    
    total_chunks = 0
    for qs in quickstarts:
        repo_name = qs.get("repo")
        qs_id = qs.get("id", repo_name)
        
        if not repo_name:
            continue
        
        # Clone or pull repo
        repo_path = clone_or_pull_repo(repo_name, quiet=args.quiet)
        
        if not repo_path:
            console.print(f"  [red]Failed to clone {repo_name}[/red]")
            continue
        
        # Index content
        try:
            chunks = index_quickstart(qs_id, repo_name, repo_path, quiet=args.quiet)
            total_chunks += chunks
        except Exception as e:
            console.print(f"  [red]Failed to index {qs_id}: {e}[/red]")
    
    console.print(f"\n[green]Indexed {total_chunks} total chunks[/green]")


def cmd_sync_coverage(args):
    """Sync feature coverage from indexed quickstart content."""
    from indexer import sync_coverage, get_coverage_freshness
    
    is_fresh, age_days = get_coverage_freshness()
    
    if args.status:
        if age_days is None:
            console.print("[yellow]Coverage has never been synced[/yellow]")
        elif is_fresh:
            console.print(f"[green]Coverage is fresh ({age_days} days old)[/green]")
        else:
            console.print(f"[yellow]Coverage is stale ({age_days} days old)[/yellow]")
        return
    
    if not args.force and is_fresh:
        console.print(f"[dim]Coverage is fresh ({age_days} days old)[/dim]")
        console.print("Use [cyan]--force[/cyan] to sync anyway")
        return
    
    sync_coverage(quiet=args.quiet)


def cmd_refresh(args):
    """Refresh all data: catalog, repos, index, coverage, and optionally re-analyze."""
    from indexer import (
        sync_catalog,
        check_catalog_freshness,
        clone_or_pull_repo,
        sync_coverage,
    )
    from indexer import index_quickstart
    from data import get_published_quickstarts
    
    console.print("[bold blue]═══ Full Data Refresh ═══[/bold blue]\n")
    
    # Step 1: Sync catalog
    console.print("[bold]Step 1/4: Syncing quickstart catalog...[/bold]")
    is_fresh, age_days = check_catalog_freshness()
    if not args.force and is_fresh:
        console.print(f"  [dim]Catalog is fresh ({age_days} days old), skipping[/dim]")
    else:
        success = sync_catalog(quiet=args.quiet)
        if not success:
            console.print("  [red]Catalog sync failed[/red]")
            if not args.continue_on_error:
                sys.exit(1)
    console.print()
    
    # Step 2: Clone/pull repos and index content
    console.print("[bold]Step 2/4: Indexing quickstart content...[/bold]")
    quickstarts = get_published_quickstarts()
    total_chunks = 0
    
    for qs in quickstarts:
        repo_name = qs.get("repo")
        qs_id = qs.get("id", repo_name)
        
        if not repo_name:
            continue
        
        repo_path = clone_or_pull_repo(repo_name, quiet=True)
        if not repo_path:
            console.print(f"  [red]Failed to clone {repo_name}[/red]")
            continue
        
        try:
            chunks = index_quickstart(qs_id, repo_name, repo_path, quiet=True)
            total_chunks += chunks
            if not args.quiet:
                console.print(f"  {qs_id}: {chunks} chunks")
        except Exception as e:
            console.print(f"  [red]Failed to index {qs_id}: {e}[/red]")
    
    console.print(f"  [green]Indexed {total_chunks} total chunks[/green]\n")
    
    # Step 3: Sync coverage
    console.print("[bold]Step 3/4: Detecting feature coverage...[/bold]")
    sync_coverage(quiet=args.quiet)
    console.print()
    
    # Step 4: Clear analysis cache
    console.print("[bold]Step 4/4: Clearing stale analysis cache...[/bold]")
    clear_analysis_store()
    console.print("  [green]Analysis cache cleared[/green]\n")
    
    # Optional: Run analysis
    if args.analyze:
        console.print("[bold]Running fresh analysis...[/bold]")
        # Create a mock args object for cmd_analyze
        class AnalyzeArgs:
            issue = None
            report = args.report
            output = args.output
            reanalyze = True  # Force fresh analysis
            no_cache = False  # Use cached GitHub data (we just synced)
            quiet = args.quiet
            no_portfolio = getattr(args, 'no_portfolio', False)
        
        cmd_analyze(AnalyzeArgs())
    else:
        console.print("[dim]Run 'issue-review analyze --report' to generate fresh analysis[/dim]")
    
    console.print("\n[bold green]═══ Refresh Complete ═══[/bold green]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze GitHub quickstart suggestion issues and generate reports."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze issues and optionally generate a PDF report",
    )
    analyze_parser.add_argument(
        "--issue", "-i",
        type=int,
        help="Analyze only a specific issue by number",
    )
    analyze_parser.add_argument(
        "--report", "-r",
        action="store_true",
        help="Generate a PDF report after analysis",
    )
    analyze_parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output path for the PDF report (implies --report)",
    )
    analyze_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass cache and fetch fresh data from GitHub",
    )
    analyze_parser.add_argument(
        "--reanalyze",
        action="store_true",
        help="Force re-analysis even if cached analysis exists",
    )
    analyze_parser.add_argument(
        "--no-portfolio",
        action="store_true",
        help="Skip portfolio-level blind spots analysis in report",
    )
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # list command
    list_parser = subparsers.add_parser(
        "list",
        help="List all quickstart suggestion issues",
    )
    list_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass cache and fetch fresh data from GitHub",
    )
    list_parser.set_defaults(func=cmd_list)
    
    # show command
    show_parser = subparsers.add_parser(
        "show",
        help="Show cached analysis for a specific issue",
    )
    show_parser.add_argument(
        "issue",
        type=int,
        help="Issue number to show",
    )
    show_parser.set_defaults(func=cmd_show)
    
    # clear-cache command
    clear_parser = subparsers.add_parser(
        "clear-cache",
        help="Clear the analysis cache",
    )
    clear_parser.set_defaults(func=cmd_clear_cache)
    
    # sync command
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync quickstart catalog from GitHub",
    )
    sync_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force sync even if catalog is fresh",
    )
    sync_parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show catalog freshness status only",
    )
    sync_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output messages",
    )
    sync_parser.set_defaults(func=cmd_sync)
    
    # index command
    index_parser = subparsers.add_parser(
        "index",
        help="Index quickstart content for RAG search",
    )
    index_parser.add_argument(
        "--quickstart", "-qs",
        type=str,
        help="Index only a specific quickstart (by ID or repo name)",
    )
    index_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output messages",
    )
    index_parser.set_defaults(func=cmd_index)
    
    # sync-coverage command
    coverage_parser = subparsers.add_parser(
        "sync-coverage",
        help="Detect and update feature coverage from indexed quickstarts",
    )
    coverage_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force sync even if coverage is fresh",
    )
    coverage_parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show coverage freshness status only",
    )
    coverage_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output messages",
    )
    coverage_parser.set_defaults(func=cmd_sync_coverage)
    
    # refresh command - chains everything together
    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Full refresh: sync catalog, index repos, detect coverage, clear cache",
    )
    refresh_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force all operations even if data is fresh",
    )
    refresh_parser.add_argument(
        "--analyze", "-a",
        action="store_true",
        help="Also run analysis after refreshing data",
    )
    refresh_parser.add_argument(
        "--report", "-r",
        action="store_true",
        help="Generate PDF report (requires --analyze)",
    )
    refresh_parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output path for PDF report",
    )
    refresh_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue refresh even if a step fails",
    )
    refresh_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress detailed output",
    )
    refresh_parser.add_argument(
        "--no-portfolio",
        action="store_true",
        help="Skip portfolio-level blind spots analysis in report",
    )
    refresh_parser.set_defaults(func=cmd_refresh)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == "__main__":
    main()
