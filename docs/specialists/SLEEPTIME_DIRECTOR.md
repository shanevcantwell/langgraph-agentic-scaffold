# Sleeptime Director Briefing: Background Model Evaluation in LAS

**Purpose:** Technical briefing on the SleeptimeDirector's role as a background orchestration agent.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-12
**Status:** Design Profile — not yet implemented. Tier 1/2 eval scripts written (uncommitted). Grounded in smoke-tested infrastructure.

---

## Executive Summary

The **SleeptimeDirector** is a ReAct-enabled orchestration agent that sits **outside** the main graph and evaluates model fitness for specialist roles. It runs during idle time (overnight, on-demand) and produces ranking artifacts for human review.

Key characteristics:
- **External agent, not a specialist** — does not participate in the graph lifecycle (no SafeExecutor, no Router routing)
- **ReAct loop with tool access** — structurally similar to ProjectDirector, but investigating models instead of user tasks
- **Three-tier evaluation** — progressively expensive: CLI battery (minutes) → react_step with real tools (minutes-hours) → full LAS integration (hours)
- **Cost-aware** — exhausts cheap measurements (embeddings, deterministic validators) before touching expensive ones (LLM-as-judge)
- **Shares infrastructure** — same MCP client pool, LLM adapters, and config as the main graph

---

## Where SleeptimeDirector Fits in the Architecture

### Not Part of the Main Graph

```
Main Graph (user-facing)              Sleeptime (background)
─────────────────────────             ──────────────────────
Triage → Facilitator → Router         SleeptimeDirector
    → Specialist → EI → Archive           ↓
         ↑                            Uses LAS as a tool
         │                            (POST /v1/graph/invoke)
    User request                           ↓
                                      Produces ranking artifacts
                                      for human review
```

### Architectural Position

The SleeptimeDirector occupies the same position as the Facilitation Agent (ADR-CORE-049):

| Concept | Facilitation Agent | Sleeptime Director |
|---------|-------------------|-------------------|
| Location | Outside graph | Outside graph |
| Purpose | Retry incomplete tasks | Evaluate model fitness |
| Invokes LLMs | Yes (prompt curation) | Yes (result analysis) |
| Loop control | max_retries, stagnation | max_iterations, budget |
| State handling | Fresh GraphState per invocation | Fresh GraphState per invocation |
| Trigger | Task completion failure | Explicit, scheduled, or event-driven |

Both inherit from a shared `BaseOrchestrationAgent` that provides: invoke LAS via API, parse results, call MCP tools, own ReAct loop with own termination logic.

### Process Hosting (Recommended: Same Process)

Managed by FastAPI lifespan alongside the main graph. Shares MCP client pool, LLM adapters, SafeExecutor. No infrastructure duplication.

Risk: crashed sleeptime could affect interactive graph. Mitigation: asyncio task isolation + exception boundaries.

---

## What the SleeptimeDirector Actually Does

### The Three-Tier Evaluation Pipeline

Each tier answers a different question with increasing cost:

```
Tier 1: CLI Battery (minutes)
  prompt → model response → drift from exemplar
  "Can this model produce the right KIND of output?"

Tier 2: MCP React Loop with Real Tools (minutes-hours)
  prompt → react_step → tool execution → observe → loop
  "Do the model's ACTIONS produce the right outcome?"

Tier 3: invoke_las Full Integration (hours)
  prompt → Triage → Router → Specialist → EI → Archive
  "Does the model work in the REAL SYSTEM end-to-end?"
```

Progressive filtering narrows the candidate pool:
```
Tier 1 → survivors → Tier 2 → survivors → Tier 3
12 models            4 models              2 models
```

### Input: Tournament Configuration

```python
@dataclass
class TournamentConfig:
    specialist_role: str              # e.g., "project_director"
    candidate_models: list[str]       # Model IDs from LM Studio manifest
    test_cases: Path                  # YAML/JSON test file path
    seeds_per_test: int = 10          # Consistency measurement
    tiers: list[int] = [1, 2]        # Which tiers to run (3 requires prerequisites)
    drift_threshold: float = 0.28    # embeddinggemma-300m calibrated
```

### Tier 1 Execution: CLI Battery

Calls prompt-prix CLI via docker exec (not MCP — batteries are batch-level, not iteration-level):

```python
async def _run_tier1(self, config: TournamentConfig) -> dict:
    cmd = [
        "docker", "exec", "prompt-prix-mcp",
        "prompt-prix-cli", "run-battery",
        "--tests", str(config.test_cases),
        "--models", ",".join(config.candidate_models),
        "--runs", str(config.seeds_per_test),
        "--output-format", "json"
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return json.loads(stdout)
```

**Proven:** 3 models x 15 tests completed in ~90 seconds via this path.

### Tier 2 Execution: Director-Mediated React Loop

Uses prompt-prix MCP's `react_step` in tool-forwarding mode. The director mediates between react_step and real MCP services:

1. Set up sandbox via filesystem MCP (known test files)
2. Call `react_step(mock_tools={})` — model produces tool calls
3. Receive `pending_tool_calls`, dispatch to filesystem/terminal MCP
4. Feed tool results back as next `react_step` observation
5. Loop until `completed=True`
6. Verify outcome: `list_directory` confirms file operations succeeded
7. Score: `compare_trajectories` on execution trace vs golden
8. Teardown sandbox

**Why the director mediates:** prompt-prix doesn't need to know about LAS's MCP endpoints. Keeps the container wall clean.

**Proven:** prompt-prix `react_step` tool-forwarding mode (`mock_tools=None`) returns `pending_tool_calls` instead of executing tools. Validated from LAS via MCP.

### Tier 3 Execution: Full LAS Integration

Calls `POST /v1/graph/invoke` with test prompt and model override:

```python
async def _run_tier3(self, test_case: dict, model_id: str) -> dict:
    response = await self.http_client.post(
        "http://localhost:8000/v1/graph/invoke",
        json={
            "input_prompt": test_case["user_request"],
            "config_overrides": {
                f"specialists.{self.specialist_role}.model": model_id
            }
        }
    )
    return response.json()
```

**Dependencies (not yet built):**
- `CompletionResult` schema on API response
- Model binding override on `/v1/graph/invoke`
- Sandbox fixture management per run

### Output: Ranking Artifacts

```python
# Written to artifacts["tournament_rankings"]
{
    "specialist_role": "project_director",
    "timestamp": "2026-02-11T03:00:00Z",
    "rankings": [
        {
            "model": "gpt-oss-20b",
            "tier1_pass_rate": 0.87,
            "tier2_pass_rate": 0.80,
            "avg_drift": 0.24,
            "avg_latency_ms": 950,
            "consistency": 0.92  # across seeds
        },
        ...
    ],
    "test_corpus": "file_categorization_drift_tests.yaml",
    "seeds": 10,
    "notes": ["gpt-oss-20b: 1 JIT-swap retry in Tier 1"]
}
```

Results written to `./logs/evaluations/` and archived alongside normal workflow archives.

---

## Tool Access

### MCP Services Used

| MCP Service | Tools | Purpose |
|-------------|-------|---------|
| **prompt-prix** (MCP) | `complete`, `react_step`, `list_models` | Iteration-level inference and ReAct primitives |
| **prompt-prix** (CLI) | `run-battery` | Batch-level battery execution (Tier 1) |
| **semantic-chunker** | `calculate_drift`, `compare_trajectories`, `analyze_trajectory`, `analyze_variants` | Drift measurement, trajectory fitness, degeneration detection |
| **filesystem** | `read_file`, `write_file`, `list_directory` | Sandbox management, result export, fixture setup |
| **terminal** | `run_command` | Docker exec, sandbox lifecycle |

### Architectural Constraint: Drift Goes Through LAS

Prompt-prix MCP's drift tools (`calculate_drift`, `analyze_variants`) delegate to semantic-chunker internally, but the prompt-prix-mcp container has no semantic-chunker connection. **Drift measurement must route through LAS's own semantic-chunker MCP.**

```
WRONG:  Director → prompt-prix MCP → (no semantic-chunker) → FAIL
RIGHT:  Director → semantic-chunker MCP → calculate_drift → OK
```

**Proven:** `calculate_drift` via prompt-prix MCP returns "semantic-chunker not available". LAS's direct semantic-chunker MCP connection is operational.

---

## Layered Validation Stack

Each layer catches what others miss. `SpecialistProfile` encodes which layers are active per role.

| Layer | Catches | Cost | Applies To |
|-------|---------|------|------------|
| **Deterministic assertions** | Malformed output, missing fields | Free | All profiles |
| **Structural validation** | Wrong operations, dependency violations | Free | Tool-calling profiles |
| **Drift from exemplar** | Subtle correctness issues | Cheap (embedding) | All profiles |
| **Trajectory analysis** | Process failures, degeneration, stalls | Cheap (embedding) | ReAct profiles |
| **Empirical outcome** | "Did it actually work?" | Medium (tool execution) | Tier 2+ |
| **LLM-as-judge** | Edge cases, novel correct answers | Expensive (inference) | Ambiguous cases only |

**Cost hierarchy principle:** Exhaust cheap measurements before touching expensive ones. For 40 runs (4 models x 10 seeds), expect ~40 embedding comparisons, structural validation on each, and maybe 5-8 LLM judge calls on ambiguous cases.

### Drift Metrics by Profile Type

| Profile Type | Metric | Example Specialists |
|-------------|--------|-------------------|
| Tool-calling | Structural comparison (action set matching, order-independent) | project_director, batch_processor |
| Natural language | Semantic embedding distance (embeddinggemma-300m 768-d) | triage, router reasoning, chat |
| Hybrid (future) | Structural on actions + semantic on reasoning | — |

**Calibration:** Correct file categorizations land at ~0.25-0.28 drift. 0.3 = semantic squelch threshold. Calibration itself is a sleeptime task (run 100+ seeds, find bimodal split between correct/incorrect, set threshold in valley).

---

## What the SleeptimeDirector Does NOT Do

| Capability | SleeptimeDirector | Who Does It |
|------------|-------------------|-------------|
| Serve user requests | No | Main graph (Triage → Router → Specialist) |
| Route specialists | No | Router |
| Modify production config | No | Human (reviews ranking artifacts, updates config.yaml) |
| Train or fine-tune models | No | Proposed: ADR-CORE-021 training infra |
| Schedule itself | No (Phase 1) | Explicit trigger; scheduler is Phase 3 |
| Coordinate GPU loading | No | Manual pre-load (Phase 1); `lms` CLI (future) |

---

## Example Flow: Tier 1 Battery Run

**Trigger:** `POST /api/sleeptime/tournament`

### Step 1: Load Configuration

Director reads tournament config specifying specialist role, candidate models, and test file.

### Step 2: Tier 1 — CLI Battery

```
[INFO] SleeptimeDirector: Starting Tier 1 for project_director
[INFO] Running battery: 4 models x 15 tests x 5 seeds = 300 test cells
[INFO] docker exec prompt-prix-mcp prompt-prix-cli run-battery --tests ... --models ... --runs 5
[INFO] Battery completed in 142s
```

prompt-prix CLI returns structured JSON with per-test pass/fail and latency. Director parses the results and applies the SpecialistProfile's `drift_tolerance` (0.28 for project_director) as the qualifying threshold.

### Step 3: Score Survivors via Drift

For models that passed the battery, Director measures semantic distance from exemplar using LAS's semantic-chunker MCP (not prompt-prix MCP — see "Drift Goes Through LAS" constraint above):

```
[INFO] Scoring survivors via semantic-chunker MCP (drift_tolerance: 0.28)
[INFO] calculate_drift(gpt-oss-20b response, exemplar) = 0.24  — within tolerance
[INFO] calculate_drift(qwen3-30b response, exemplar) = 0.27  — within tolerance
[INFO] calculate_drift(devstral-24b response, exemplar) = 0.31  — above squelch threshold (0.30)
[WARN] devstral-24b flagged: drift exceeds semantic squelch threshold
```

The 0.30 squelch threshold is calibrated from embeddinggemma-300m 768-d space (see Drift Metrics by Profile Type above). Scores above it indicate the response is semantically distant enough from the exemplar to warrant human review.

### Step 4: Write Rankings

Rankings written to `./logs/evaluations/tournament_project_director_20260211.json`. Human reviews next morning.

---

## Trigger Mechanisms

### Phase 1: Explicit (Current Target)

```
POST /api/sleeptime/tournament
{
    "specialist_role": "project_director",
    "candidate_models": ["gpt-oss-20b", "qwen3-30b-a3b-instruct-2507"],
    "test_file": "tests/prompt-prix/file_categorization_drift_tests.yaml",
    "tiers": [1]
}
```

Deterministic, scriptable, no LLM deciding how to handle the request.

### Phase 3: Event-Driven (Future)

- Archive creation hook emits event → scheduler queues evaluation
- New model detected in LM Studio → scheduler queues qualifying battery
- Prompt file changed in git → scheduler queues regression test
- Scheduled intervals (cron-like: "run nightly")

---

## GPU Resource Strategy

`PooledLMStudioAdapter` with `local-inference-pool` provides least-loaded balancing across RTX 8000 + RTX 3090.

**Phase 1:** Time partitioning (simplest). Sleeptime runs overnight when no interactive contention. Pre-load 4 survivor models manually before tournament.

**Future:** Priority queue — interactive workflows preempt background evaluation. Background tasks yield when interactive needs inference.

---

## Configuration Reference

### Proposed Directory Structure

```
app/src/orchestration/
├── base_orchestration_agent.py   # Shared: invoke LAS, parse results, tool access
├── facilitation_agent.py         # ADR-049: retry incomplete tasks (coexists)
└── sleeptime/
    ├── director.py               # ReAct agent: evaluate models via batteries + LAS runs
    ├── profiles.py               # SpecialistProfile definitions with drift config
    ├── validators.py             # Structural validators + reasoning stripping
    └── scheduler.py              # Triggers: API endpoint, cron, archive events
```

### SpecialistProfile (Proposed)

```python
@dataclass
class SpecialistProfile:
    role: str                                           # e.g., "project_director"
    drift_tolerance: float                              # e.g., 0.28
    drift_metric: Literal["semantic", "structural"]     # by profile type
    validation_stack: list[str]                          # active layers
    test_cases: Path                                    # per-role test file
    exemplar_source: str                                # "hand_crafted" | "archive_extracted"
```

### API Endpoint (Phase 1)

```python
@app.post("/api/sleeptime/tournament")
async def run_tournament(config: TournamentConfig):
    task = asyncio.create_task(sleeptime_director.run(config))
    return {"status": "started", "task_id": str(task.get_name())}
```

### External Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| prompt-prix CLI | **Smoke-tested** | Battery execution via `docker exec` proven |
| prompt-prix MCP | **Smoke-tested** | `list_models` (59ms), `complete` (250ms), `react_step` tool-forwarding proven |
| semantic-chunker MCP | **Available** | LAS has direct connection; prompt-prix MCP path blocked |
| filesystem MCP | **Available** | Sandbox setup/teardown |
| Tier 1 shell wrapper | **Written** | `scripts/run_tier1_battery.sh` (uncommitted, shelved for #170) |
| Tier 2 eval runner | **Written** | `scripts/run_tier2_eval.py` (uncommitted, shelved for #170) |
| 13-file benchmark | **Written** | `tests/prompt-prix/react_file_categorization_13_benchmark.json` (uncommitted) |
| `CompletionResult` schema | **Not built** | Needed for Tier 3 only |
| Model override on invoke | **Not built** | Needed for Tier 3 only |
| react_step tool-forwarding | **Built & validated** | prompt-prix `mock_tools=None` returns `pending_tool_calls` |

---

## Key References

| Document | Purpose |
|----------|---------|
| [sleeptime-architecture-options.md](../ADRs/proposed/sleeptime-architecture-options.md) | 8 decision levels from architecture discussion |
| [PROPOSAL_Eval-Architecture-And-Sleeptime-Subgraph.md](../proposals/PROPOSAL_Eval-Architecture-And-Sleeptime-Subgraph.md) | Eval pipeline design, open questions |
| ADR-CORE-049 | Facilitation-as-Tool (shared base pattern) |
| ADR-CORE-056 | Model Tournament vision (profiles, archive extraction, validators) |
| ADR-CORE-066 | Sleeptime Autonomous Orchestration (Phase 6 target) |
| ADR-CORE-068 | Shared GPU Pool (PooledLMStudioAdapter, proven) |
| [scripts/smoke_test_mcp.py](../../scripts/smoke_test_mcp.py) | MCP connectivity smoke test |

### Key Files (Existing — Uncommitted)

| File | Purpose |
|------|---------|
| [scripts/run_tier1_battery.sh](../../scripts/run_tier1_battery.sh) | Shell wrapper for CLI battery runs |
| [scripts/run_tier2_eval.py](../../scripts/run_tier2_eval.py) | Async Python runner for real filesystem dispatch |
| [tests/prompt-prix/react_file_categorization_13_benchmark.json](../../tests/prompt-prix/react_file_categorization_13_benchmark.json) | 13-file/7-category benchmark (Tier 1 + Tier 2) |
| [tests/prompt-prix/react_file_categorization_benchmark.json](../../tests/prompt-prix/react_file_categorization_benchmark.json) | 6-file/3-category benchmark (5 scenarios) |
| [tests/prompt-prix/file_categorization_drift_tests.yaml](../../tests/prompt-prix/file_categorization_drift_tests.yaml) | Single-pass drift tests (4 cases) |

### Key Files (Proposed — Not Yet Created)

| File | Purpose |
|------|---------|
| `app/src/orchestration/base_orchestration_agent.py` | Shared invoke/parse/tool infrastructure |
| `app/src/orchestration/sleeptime/director.py` | SleeptimeDirector ReAct agent |
| `app/src/orchestration/sleeptime/profiles.py` | SpecialistProfile definitions |
| `app/src/orchestration/sleeptime/validators.py` | Structural validators + reasoning stripping |
| `app/src/orchestration/sleeptime/scheduler.py` | Trigger mechanisms |

---

## Summary

The SleeptimeDirector is an **external ReAct agent** that:

1. Receives a tournament configuration (specialist role, candidate models, test cases)
2. Runs a three-tier evaluation pipeline with progressive filtering
3. Scores results using a layered validation stack (deterministic → embedding → LLM judge)
4. Produces ranking artifacts for human review
5. Does NOT modify production configuration — human remains in the deployment loop

It shares the main graph's infrastructure (MCP, adapters, config) but has its own execution context, loop control, and termination logic. The same architectural pattern as the Facilitation Agent (ADR-049) — both are "agents that use LAS as a tool."
