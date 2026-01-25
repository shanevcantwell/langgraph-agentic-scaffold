# Facilitator Briefing: How Context Gathering Works in LAS

**Purpose:** Technical briefing on the Facilitator specialist's role in the LAS execution flow.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Date:** 2026-01-15

---

## Executive Summary

The **Facilitator** is a deterministic, non-LLM specialist that bridges intent classification (Triage) and task execution (Router). Its sole job is to **autonomously gather background context** before the system decides how to handle a user request.

Key characteristics:
- **Procedural, not LLM-based** — executes a plan, doesn't reason
- **MCP orchestrator** — calls internal and external services via Model Context Protocol
- **Context collector, not task executor** — gathers information but doesn't solve problems
- **Single-pass execution** — runs once per request, no internal loops

---

## Where Facilitator Fits in the Execution Flow

### The Context Engineering Subgraph

```
User Request
    ↓
TriageArchitect (LLM: classifies intent, creates ContextPlan)
    ↓
    [Does ContextPlan have actions?]
    ├─ YES → Facilitator → DialogueSpecialist → Router
    └─ NO  → Router (direct)
```

### Routing Decision Logic

The routing decision is made in `check_triage_outcome()` ([graph_orchestrator.py:33](../app/src/workflow/graph_orchestrator.py#L33)):

```python
def check_triage_outcome(self, state: GraphState) -> str:
    context_plan_data = state.get("artifacts", {}).get("context_plan")

    if context_plan_data:
        plan = ContextPlan(**context_plan_data)
        if plan.actions:  # Any actions at all trigger Facilitator
            return "facilitator_specialist"

    return "router_specialist"  # No context needed
```

**Important:** ALL plans with actions route through Facilitator, including those with only `ASK_USER` actions. The Facilitator processes automated actions and passes through `ASK_USER` for DialogueSpecialist to handle.

---

## What the Facilitator Actually Does

### Input: ContextPlan Artifact

TriageArchitect produces a `context_plan` artifact in GraphState:

```python
# From context_schema.py
class ContextPlan(BaseModel):
    actions: List[ContextAction]           # What to gather
    reasoning: str                         # Why (for observability)
    recommended_specialists: List[str]     # Hint for Router after context gathered

class ContextAction(BaseModel):
    type: ContextActionType   # RESEARCH | READ_FILE | SUMMARIZE | LIST_DIRECTORY | ASK_USER
    target: str               # Query, file path, or text
    description: str          # Why this action is needed
    strategy: Optional[str]   # Provider hint (e.g., "google", "duckduckgo")
```

### Execution: Action-by-Action Processing

The Facilitator iterates through `context_plan.actions` and executes each:

| Action Type | MCP Service Called | Result |
|-------------|-------------------|--------|
| `RESEARCH` | Internal: `web_specialist.search(query)` | Web search results formatted as markdown links |
| `READ_FILE` | External: `filesystem.read_file(path)` | File contents in code block |
| `SUMMARIZE` | Internal: `summarizer_specialist.summarize(text)` | Condensed summary (see note below) |
| `LIST_DIRECTORY` | External: `filesystem.list_directory(path)` | Markdown bullet list of entries |
| `ASK_USER` | **Skipped** — handled by DialogueSpecialist | Passes through unchanged (implicit skip) |

**SUMMARIZE file path heuristic:** If the target looks like a file path (starts with `/` or `./`), Facilitator attempts to read the file first via filesystem MCP, then summarizes the content. This allows `SUMMARIZE /docs/README.md` to work as expected.

**ASK_USER implicit skip:** There's no explicit handler for `ASK_USER` in the action loop — it simply falls through without producing output. DialogueSpecialist handles these actions downstream.

### Output: gathered_context Artifact

After processing all actions, Facilitator produces:

```python
{
    "artifacts": {
        "gathered_context": """### Research: quantum computing trends
- [Article 1](https://...) : Recent breakthroughs...
- [Article 2](https://...) : IBM announces...

### File: /workspace/config.yaml
```yaml
project:
  name: example
```

### Directory: /workspace/docs
- README.md
- API.md
- ARCHITECTURE.md
"""
    },
    "scratchpad": {
        "facilitator_complete": True
    }
}
```

---

## MCP Integration Details

### Internal MCP (Python services in-process)

Called via `self.mcp_client.call()`:

```python
# Web search
results = self.mcp_client.call(
    service_name="web_specialist",
    function_name="search",
    query="quantum computing 2026"
)

# Summarization
summary = self.mcp_client.call(
    service_name="summarizer_specialist",
    function_name="summarize",
    text=long_document
)
```

### External MCP (Containerized services via stdio)

Called via the sync-to-async bridge `sync_call_external_mcp()`, with results parsed by `extract_text_from_mcp_result()`:

```python
# File read (ADR-CORE-035: uses official Anthropic MCP filesystem server)
content = sync_call_external_mcp(
    self.external_mcp_client,
    "filesystem",
    "read_file",
    {"path": "/workspace/config.yaml"}
)
```

The sync bridge ([mcp/external_client.py:462](../app/src/mcp/external_client.py#L462)) handles the async-to-sync translation:
- Facilitator code is synchronous (LangGraph node execution)
- External MCP uses async stdio transport
- `asyncio.run_coroutine_threadsafe()` schedules calls on the main event loop

### Special Case: In-Memory Artifacts

Before calling filesystem MCP, Facilitator checks if the target exists as an in-memory artifact:

```python
# From facilitator_specialist.py:110-133
if artifact_key in artifacts:
    content = artifacts[artifact_key]  # Use in-memory version
else:
    content = self._read_file_via_filesystem_mcp(target_path)  # Filesystem
```

This handles uploaded images (stored as base64) and other artifacts that never touch the filesystem.

---

## Error Handling and Graceful Degradation

### Service Unavailability

If external filesystem MCP is not connected:

```python
def _read_file_via_filesystem_mcp(self, path: str) -> Optional[str]:
    if not self._is_filesystem_available():
        logger.warning("Facilitator: Filesystem MCP not available")
        return None  # Graceful fail
```

The gathered_context will include: `### File: /path\n[Filesystem service unavailable]`

### Action Execution Failures

Individual action failures don't halt the entire plan:

```python
try:
    # Execute action...
except Exception as e:
    gathered_context.append(f"### Error: {action.target}\nFailed to execute: {e}")
    # Continue with next action
```

---

## What the Facilitator Does NOT Do

Understanding boundaries is critical:

| Capability | Facilitator | Who Does It |
|------------|-------------|-------------|
| LLM reasoning | No | TriageArchitect, Router, Specialists |
| Routing decisions | No | Router |
| User interaction | No | DialogueSpecialist |
| Task completion loops | No | Proposed: External Facilitation Agent (ADR-CORE-049) |
| Prompt curation/retry | No | Proposed: External Facilitation Agent (ADR-CORE-049) |
| Direct GraphState mutation | No | SafeExecutor/NodeExecutor |

---

## Example Flow: File Read Request

**User prompt:** "Read the contents of README.md"

### Step 1: TriageArchitect

Produces `context_plan` artifact:

```json
{
  "actions": [
    {
      "type": "read_file",
      "target": "README.md",
      "description": "User explicitly requested file contents"
    }
  ],
  "reasoning": "User wants to see file contents before further processing",
  "recommended_specialists": ["chat_specialist"]
}
```

### Step 2: check_triage_outcome

`plan.actions` is non-empty → routes to `"facilitator_specialist"`

### Step 3: Facilitator Execution

```
[INFO] Facilitator: Executing plan with 1 actions.
[INFO] Facilitator: Executing action read_file -> README.md
[INFO] sync_call_external_mcp: Calling filesystem.read_file
```

Produces:

```json
{
  "artifacts": {
    "gathered_context": "### File: README.md\n```\n# LAS Project\n...\n```"
  }
}
```

### Step 4: DialogueSpecialist

Checks for `ASK_USER` actions. None found → passes through (no-op).

### Step 5: Router

Sees `gathered_context` artifact. Routes to `chat_specialist` (or per `recommended_specialists`).

### Step 6: ChatSpecialist

Presents file contents to user with appropriate formatting.

---

## Archive Forensics

Every workflow run produces an archive at `./logs/archive/run_YYYYMMDD_HHMMSS_<hash>.zip`.

To verify Facilitator execution:

```bash
# Check routing history
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'
# Look for: ["triage_architect", "facilitator_specialist", "dialogue_specialist", "router_specialist", ...]

# Check gathered context (in final_state or as separate artifact)
unzip -l ./logs/archive/run_*.zip
# May include: gathered_context.md or embedded in final_state.json
```

**Note:** Facilitator is procedural, so `llm_traces.jsonl` will NOT contain Facilitator entries (no LLM calls). Only specialists that invoke models appear in traces.

---

## Relationship to ADR-CORE-049 (Proposed)

**ADR-CORE-049** proposes a different concept: **Facilitation-as-Tool** — an external agent that uses LAS as a tool for retry/refinement loops.

| Concept | Current Facilitator | Proposed Facilitation Agent |
|---------|--------------------|-----------------------------|
| Location | Inside graph | Outside graph (uses API) |
| Purpose | Gather context once | Retry incomplete tasks |
| Invokes LLMs | No | Yes (prompt curation) |
| Loop control | None (single pass) | max_retries, stagnation detection |
| State handling | Writes to GraphState | Fresh GraphState per invocation |

**The current Facilitator and proposed Facilitation Agent serve different purposes and would coexist if ADR-CORE-049 is implemented.**

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  facilitator_specialist:
    is_enabled: true
    type: "procedural"  # No LLM config needed
```

### External MCP (filesystem)

```yaml
mcp:
  external_mcp:
    enabled: true
    services:
      filesystem:
        command: "docker"
        args: ["run", "-i", "--rm", "-v", "/workspace:/workspace", "mcp/filesystem", "/workspace"]
```

### Dependency Injection

`external_mcp_client` is injected by GraphBuilder after specialist instantiation:

```python
# In GraphBuilder initialization
for instance in self.specialists.values():
    instance.external_mcp_client = self.external_mcp_client
```

---

## Key Files

| File | Purpose |
|------|---------|
| [facilitator_specialist.py](../app/src/specialists/facilitator_specialist.py) | Facilitator implementation |
| [context_schema.py](../app/src/interface/context_schema.py) | ContextPlan/ContextAction schemas |
| [context_engineering.py](../app/src/workflow/subgraphs/context_engineering.py) | Subgraph edge definitions |
| [graph_orchestrator.py](../app/src/workflow/graph_orchestrator.py) | `check_triage_outcome()` routing logic |
| [external_client.py](../app/src/mcp/external_client.py) | `sync_call_external_mcp()` bridge |
| [mcp/utils.py](../app/src/mcp/utils.py) | `extract_text_from_mcp_result()` helper |

---

## Summary

The Facilitator is a **procedural MCP orchestrator** that:

1. Receives a `ContextPlan` from TriageArchitect
2. Executes automated context-gathering actions (RESEARCH, READ_FILE, SUMMARIZE, LIST_DIRECTORY)
3. Produces a `gathered_context` artifact
4. Passes control to DialogueSpecialist (for user clarification) then Router

It does NOT make decisions, invoke LLMs, or loop. It simply gathers the background information needed for downstream specialists to do their work.
