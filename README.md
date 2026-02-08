# Quickstart Suggestion Issue Review Tool

A multi-agent LLM system that analyzes GitHub issues proposing new AI quickstarts against an existing catalog. Built with LangGraph for agent orchestration and designed for deployment on OpenShift AI.

## How It Works

### Overview

```mermaid
flowchart TD
    A[Data Loading] --> B[Portfolio Analyst]
    B -->|portfolio_gaps| C

    subgraph C [Parallel Issue Analysis - up to 6 concurrent]
        direction LR
        I1[Issue #1] ~~~ I2[Issue #2] ~~~ IN[Issue #N]
    end

    C --> D[PDF Report]
```

The tool runs in four stages: load data from GitHub and the local catalog, analyze the portfolio for blind spots, evaluate each issue in parallel, and generate a PDF report.

### Per-Issue Analysis

Each issue is analyzed by three specialist agents running in parallel, then synthesized by the Coordinator:

```mermaid
flowchart TD
    START([GitHub Issue]) --> TA & PP & PS

    TA[Technical Analyst<br/><br/>Overlap check<br/>Dev stage<br/>Similar stack<br/>RAG tool calls]
    PP[Persona Panel<br/><br/>6 non-technical<br/>personas evaluate<br/>broad appeal]
    PS[Platform Specialist<br/><br/>Feature identification<br/>Platform fit<br/>New vs. reused]

    TA & PP & PS --> CO

    CO[Coordinator<br/><br/>Synthesize results<br/>Priority scoring<br/>Gap detection]

    CO --> END([Final Analysis])
```

| Agent | What it does | Output |
|-------|-------------|--------|
| **Portfolio Analyst** | Analyzes the overall catalog for blind spots; runs once before individual analyses | Industry gaps, missing use cases, undemonstrated capabilities, strategic observations |
| **Technical Analyst** | Compares a proposal against existing quickstarts using RAG tools for deep search | Overlap level, development stage, related quickstarts, clarification points |
| **Persona Panel** | 6 non-technical professional personas evaluate if they'd understand and use this | Broad appeal rating, which personas resonate vs. don't |
| **Platform Specialist** | Identifies which OpenShift AI features a proposal would demonstrate | Platform fit, identified features, new vs. already-covered |
| **Coordinator** | Synthesizes all agent outputs, scores priority, detects portfolio gap coverage | Priority (Low/Medium/High), portfolio gap matches |

The Technical Analyst uses LLM tool-calling to search a vector index of published quickstart content (semantic search, README lookups, code inspection) over multiple rounds of research. The Platform Specialist and Persona Panel use direct prompting without tools.

### Execution Flow

```mermaid
flowchart TD
    subgraph S1 [Step 1: Data Loading]
        GH[Fetch GitHub issues] --> CAT[Load quickstart catalog]
        CAT --> REPO[Fetch org repositories]
        REPO --> FEAT[Load features + coverage]
    end

    subgraph S2 [Step 2: Portfolio Analysis]
        PA[Build catalog context] --> LLM1[LLM: strategic gap analysis]
        LLM1 --> GAPS[Extract portfolio_gaps dict]
    end

    subgraph S3 [Step 3: Parallel Issue Analysis]
        direction TB
        CHK{Cached?}
        CHK -->|Yes| USE[Return cached result]
        CHK -->|No| GRAPH[Run per-issue LangGraph]
        GRAPH --> CACHE[Cache result]
    end

    subgraph S4 [Step 4: Report Generation]
        COLLECT[Collect all analyses] --> PDF[Generate PDF report]
    end

    S1 --> S2 --> S3 --> S4
```

**Step 1 — Data Loading.** GitHub issues are fetched from the `rh-ai-quickstart` organization. The published quickstart catalog is loaded from `data/catalog.yaml` (synced from [ai-quickstart-pub](https://github.com/rh-ai-quickstart/ai-quickstart-pub)). Organization repositories, the feature catalog (`data/features.yaml`), and the coverage matrix (`data/coverage.yaml`) are also loaded. All GitHub data is cached locally.

**Step 2 — Portfolio Analysis.** The Portfolio Analyst receives a description of every published quickstart and produces a strategic gap analysis: underserved industries, missing use cases, undemonstrated capabilities, and expected adjacent quickstarts. The result is cached and a simplified `portfolio_gaps` dict is passed into every issue analysis.

**Step 3 — Parallel Issue Analysis.** Each issue is checked against the cache first. Uncached issues enter the per-issue LangGraph where all three specialist agents run in parallel. Once they finish, the Coordinator merges their outputs, applies a consistency check (e.g., if use case overlaps are listed, overlap level cannot be "Unique"), matches the issue against portfolio gaps, and calculates a priority score. The final result is cached.

**Step 4 — Report Generation.** If `--report` is passed, all analyses are collected and rendered into a PDF containing a portfolio blind spots section, a summary table, and detailed per-issue breakdowns.

### Content Indexing

The `refresh` command prepares the data pipeline that powers the Technical Analyst's RAG tools:

```mermaid
flowchart LR
    SYNC[sync<br/>Fetch catalog from<br/>ai-quickstart-pub] --> INDEX[index<br/>Clone repos, extract<br/>content, embed chunks]
    INDEX --> COV[sync-coverage<br/>Detect features in<br/>indexed quickstarts]
    COV --> READY([Ready for analysis])
```

The indexer extracts content from each quickstart repository (READMEs, Helm charts, notebooks, dependency files, config templates), chunks it with markdown-aware splitting, and embeds it into PostgreSQL with pgvector for similarity search.

## Analysis Output

Each issue analysis produces the following fields, which appear in both the PDF report and the cached JSON:

| Field | Values | Description |
|-------|--------|-------------|
| Suggested Priority | Low / Medium / High | Overall priority based on overlap, stage, appeal, features, and gap coverage |
| Overlap Level | Unique / Possible Overlap / Unclear | Whether the proposal's use case overlaps with existing quickstarts |
| Development Stage | Has Code / Detailed Plan / Detailed Concept / Concept Summary | How mature the proposal is |
| Broad Appeal | Universal / Business Specific / Technical Only | How broadly non-technical professionals would find it relevant |
| Platform Fit | Excellent / Good / Moderate / Poor | How well the proposal demonstrates OpenShift AI features |
| Summary | text | Neutral summary of the contributor's proposal |
| Further Info | text | What additional detail would strengthen the proposal, if any |
| Use Case Overlap | list | Existing quickstarts with similar business problems |
| Similar Stack | list | Existing quickstarts sharing technologies but different use cases |
| Platform Features | list | OpenShift AI features identified, with new vs. already-covered |
| Fills Catalog Gaps | list | Portfolio blind spots this proposal would address |
| Identified Gaps | list | Opportunities the proposal could fill |
| Audience | list | Which personas relate to the proposal and which don't |

Priority is scored from factors including overlap level, development stage, audience appeal, new platform feature demonstrations, and portfolio gap coverage, then mapped to Low/Medium/High.

## Getting Started

### Installation

```bash
git clone <repo-url>
cd issue-review
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

**Required:**

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT with repo access to rh-ai-quickstart org |
| `LLM_BASE_URL` | LLM endpoint (any OpenAI-compatible API) |
| `LLM_API_KEY` | API key for the LLM endpoint |
| `LLM_MODEL` | Model identifier |

The tool works with any OpenAI-compatible endpoint (Anthropic, OpenAI, vLLM, Ollama). See `.env.example` for provider-specific examples.

**Optional:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection (default: `postgresql://issue_review:issue_review@localhost:5432/issue_review`) |
| `LANGFUSE_PUBLIC_KEY` | Langfuse observability |
| `LANGFUSE_SECRET_KEY` | Langfuse observability |
| `LANGFUSE_HOST` | Langfuse host URL |

### Usage

```bash
# 1. Start PostgreSQL
docker-compose up -d

# 2. Initialize data (sync catalog, index repos, detect coverage)
issue-review refresh

# 3. Analyze all issues and generate a PDF report
issue-review analyze --report

# Analyze a specific issue
issue-review analyze -i 42

# Force re-analysis (ignore cache)
issue-review analyze --reanalyze --report
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `refresh` | Full refresh: sync catalog, index repos, detect coverage, clear analysis cache |
| `list` | List quickstart suggestion issues with analysis status |
| `analyze` | Run multi-agent analysis on issues |
| `show <issue>` | Display cached analysis for an issue |
| `sync` | Sync published quickstarts from ai-quickstart-pub repo |
| `index` | Clone repos and index content (README, Helm, notebooks, deps) |
| `sync-coverage` | Detect and update feature coverage from indexed quickstarts |
| `clear-cache` | Clear analysis cache (both issue analyses and portfolio analysis) |

<details>
<summary>Analyze options</summary>

| Option | Description |
|--------|-------------|
| `--issue, -i` | Analyze specific issue number |
| `--report, -r` | Generate PDF report after analysis |
| `--output, -o` | Custom output path for PDF |
| `--reanalyze` | Force re-analysis, ignoring cache |
| `--no-cache` | Bypass GitHub API cache |
| `--no-portfolio` | Skip portfolio-level blind spots analysis |

</details>

<details>
<summary>Refresh options</summary>

| Option | Description |
|--------|-------------|
| `--force, -f` | Force all operations even if data is fresh |
| `--analyze, -a` | Also run analysis after refreshing data |
| `--report, -r` | Generate PDF report (requires --analyze) |
| `--no-portfolio` | Skip portfolio-level blind spots analysis |
| `--continue-on-error` | Continue refresh even if a step fails |

</details>

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agent Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM Interface | OpenAI-compatible API (Anthropic, OpenAI, vLLM, Ollama) |
| Vector Store | PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) |
| Embeddings | [sentence-transformers](https://www.sbert.net/) |
| Observability | [Langfuse](https://langfuse.com/) (optional) |
| PDF Generation | [fpdf2](https://pyfpdf.github.io/fpdf2/) |

## Project Structure

```
issue-review/
├── main.py                  # CLI entry point
├── config.py                # Environment variable loading
├── prompts.py               # All LLM prompt templates
├── report_generator.py      # PDF report rendering
├── comment_generator.py     # GitHub comment formatting
├── analysis_store.py        # Analysis caching (thread-safe)
├── data_sources.py          # GitHub API data fetching
├── agents/
│   ├── state.py             # Shared state types and dataclasses
│   ├── graph.py             # Per-issue LangGraph (parallel agents → coordinator)
│   ├── report_graph.py      # Top-level orchestrator (portfolio → parallel issues)
│   ├── technical.py         # Technical Analyst agent
│   ├── personas.py          # Persona Panel agent
│   ├── platform.py          # Platform Specialist agent
│   ├── portfolio.py         # Portfolio Analyst agent
│   └── coordinator.py       # Coordinator (synthesis + scoring)
├── llm/
│   ├── client.py            # OpenAI-compatible LLM client
│   ├── tools.py             # Tool-calling infrastructure
│   ├── parsing.py           # JSON extraction from LLM responses
│   ├── callbacks.py         # Langfuse tracing integration
│   └── guardrails.py        # Content safety validation
├── tools/
│   ├── research.py          # RAG tools (semantic search, README, code)
│   └── features.py          # Feature catalog tools
├── indexer/
│   ├── content.py           # Content extraction and chunking
│   ├── embeddings.py        # Embedding generation and vector storage
│   ├── sync.py              # Catalog sync from GitHub
│   └── coverage.py          # Feature coverage detection
├── data/
│   ├── catalog.yaml         # Published quickstart catalog
│   ├── features.yaml        # OpenShift AI feature definitions
│   ├── coverage.yaml        # Feature coverage matrix
│   └── personas.yaml        # Persona definitions
├── cache/                   # Runtime caches (gitignored)
├── reports/                 # Generated PDFs (gitignored)
├── .env.example             # Environment template
├── pyproject.toml           # Dependencies and project metadata
└── docker-compose.yml       # PostgreSQL + pgvector
```

## Adding Agents, Personas, or other Contributions

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidance on adding personas, features, agents, and tools.
