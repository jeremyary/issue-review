# Contributing

## Adding Personas

Edit `data/personas.yaml` to add new non-technical personas. Each persona evaluates suggestions independently during the Persona Panel stage.

```yaml
- id: education_professional
  name: Education Professional
  examples:
    - university administrator
    - instructional designer
  system_prompt: |
    You are an education professional evaluating...
```

## Adding Platform Features

Edit `data/features.yaml` to track new OpenShift AI capabilities. The Platform Specialist uses these definitions to identify which features a proposal would demonstrate.

```yaml
- id: model_registry
  name: Model Registry
  category: Model Management
  description: Central repository for model versioning, metadata, and lifecycle tracking
  keywords:
    - model registry
    - model versioning
    - model metadata
```

After adding features, run `issue-review sync-coverage` to detect which existing quickstarts already demonstrate them.

## Adding Agents

Create a new module in `agents/` and wire it into the per-issue graph in `agents/graph.py`:

```python
workflow.add_node("my_agent", my_agent_node)
workflow.add_edge(START, "my_agent")
workflow.add_edge("my_agent", "coordinator")
```

The agent node receives `AnalysisState` and returns a dict of state updates. All specialist agents run in parallel before the Coordinator.

## Creating Tools

Tools are used by the Technical Analyst via LLM function calling. Create new tools in `tools/`:

```python
from llm.tools import Tool

def my_function(param1: str, param2: int = 5) -> str:
    """Tool implementation - must return a JSON string."""
    import json
    result = {"status": "ok", "data": f"{param1} * {param2}"}
    return json.dumps(result)

my_tool = Tool(
    name="my_function",
    description="Description of what this tool does",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "First parameter"},
            "param2": {"type": "integer", "description": "Optional second param", "default": 5},
        },
        "required": ["param1"],
    },
    function=my_function,
)
```

Then pass the tool to an agent via `chat_with_tools`:

```python
from llm.tools import chat_with_tools
from llm.client import get_client, get_model

response, history = chat_with_tools(
    client=get_client(),
    model=get_model(),
    messages=[{"role": "user", "content": "..."}],
    tools=[my_tool],
    max_iterations=10,
)
```

The tool loop runs up to `max_iterations` rounds of LLM tool calls. If the limit is reached without a final response, one additional call is made without tools to force a completion.

## Caching

The tool uses a multi-layer cache to avoid redundant API calls and LLM invocations:

| Cache | File | Cleared by |
|-------|------|------------|
| GitHub issues | `cache/issues.json` | `--no-cache`, `refresh` |
| Org repositories | `cache/repositories.json` | `--no-cache`, `refresh` |
| Portfolio analysis | `cache/portfolio_analysis.json` | `--reanalyze`, `clear-cache`, `refresh` |
| Issue analyses | `cache/analyses.json` | `--reanalyze` (per issue), `clear-cache`, `refresh` |

All cache writes use a threading lock to ensure safety during parallel analysis.

## Priority Scoring

The Coordinator calculates priority from a base score of 4 with the following adjustments:

| Factor | Effect |
|--------|--------|
| Overlap: Unique | +1 |
| Overlap: Unclear | -1 |
| Stage: Has Code | +2 |
| Stage: Detailed Plan | +1 |
| Stage: Concept Summary | -3 |
| Appeal: Universal | +1 |
| Appeal: Technical Only | -1 |
| New platform features | Up to +2 |
| Fills portfolio gaps | Up to +2 |

The raw score is clamped to 1-10, then mapped: **8-10 = High**, **5-7 = Medium**, **1-4 = Low**.

See `agents/coordinator.py` for the full implementation.
