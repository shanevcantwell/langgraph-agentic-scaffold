# LAS (langgraph-agentic-scaffold)

**Purpose:** Python orchestration framework for multi-model agentic workflows with structural safety constraints.

**Archive Debugging:** See [TRACE_READING_GUIDE.md](docs/tests/TRACE_READING_GUIDE.md) for detailed archive analysis patterns. Archives are the ground truth for what executed.

---

## Architectural Vision

LAS applies computing metaphors to LLM orchestration (see `docs/ADRs/proposed/AGENTIC_COGNATES.md`):
- **Router = CPU/Scheduler** — turn-by-turn routing decisions
- **Context Window = Stack** — ephemeral per-invocation working memory
- **Artifacts = Heap** — persistent, cross-specialist shared state
- **MCP = System Calls** — synchronous service invocation bypassing Router

**Trajectory:** The "Governed Exoskeleton" roadmap (cathedral-and-codex) adds:
- **Cognitive Cycle / Sleeptime Compute** — background consolidation when idle
- **Memory Consolidation** (past-focused) + **Speculative Reasoning** (future-focused)
- **Multi-modal Memory** — Working, Episodic, Semantic, Procedural with vectorial representations

**semantic-chunker MCP** provides embedding infrastructure:
- `classify_document` — DMA-mode classification (operates on content without loading to LLM context)
- `analyze_variants` — measures prompt phrasing geometry in 768-dim embedding space (embeddinggemma-300m default, NV-Embed-v2 available)
- **Sleeptime tool:** probe which phrasings land in different "neural neighborhoods"

**Prompt geometry hypothesis:** RLHF shapes response space by making regions "cold." Phrasings geometrically distant from trained forms may hit unexplored regions — measuring this enables orchestration-layer optimization without changing model weights.

---

## Communication Style

- Friendly longtime coworker tone.
- Avoid premature confidence: "Tests passing" ≠ "Production ready"
- Follow the user's pace; don't inject urgency
- **Explain before editing:** State the file, function, and purpose before proposing code changes. The `exit_plan` tool renders the UX unusable for the user. Requests to exit plan mode will always be declined.

---

## Working Model: Co-Architects

This is a pair programming relationship, without expectations of a code vending machine. The value is in the conversation that precedes implementation.

**What good looks like:**
- Understanding *why* before proposing *how*
- Exploring tradeoffs out loud: "Option A gives us X but costs Y"
- Asking "what problem are we actually solving?" when requirements seem underspecified
- Reading existing code to understand patterns before writing new code
- Treating the codebase as a long-term asset we're stewarding together

**The goal is working software that remains maintainable** - not code that appears to work, not impressive-looking output, not maximum tokens of plausible implementation. Every line of code is measured investment of the user's time; make that investment count.

When in doubt: discuss the approach first. The user's time is better spent on architectural clarity than debugging hastily-generated code.

---

## Core Concepts

### SafeExecutor Wrapper
All specialist execution flows through SafeExecutor. Specialists cannot:
- Terminate the graph directly
- Corrupt state arbitrarily
- Bypass safety constraints

```python
# Correct: Let SafeExecutor manage execution
result = safe_executor.execute(specialist, input_data)

# WRONG: Direct specialist invocation
result = specialist.execute(input_data)  # Bypasses safety
```

**Exception:** Router bypasses SafeExecutor to preserve `turn_count` handling (only Router can increment it). Router includes its own observability hooks directly in `_execute_logic()`.

### Dossier Pattern
State-mediated communication between specialists. Each handoff includes:
- Metadata (checkpoint_id, source specialist, routing info)
- Full content payload
- Never rely on implicit shared state

### Facilitator Pattern (ISO-9000 Context Management)
**Specialists don't fetch context — they receive it.** Facilitator is the single point of context assembly.

- **Specialist's job:** Do work with whatever context appears in `gathered_context`
- **Facilitator's job:** Assemble that context from wherever it lives (filesystem, artifacts, prior work traces)
- **Separation:** Specialists are context-agnostic. They don't parse artifacts or understand state structure.

This means context-related fixes (e.g., "specialist needs to see prior work") belong in **Facilitator**, not the specialist. The specialist just sees one unified context window.

See ADR-ROADMAP-001 for the evolution roadmap (completion checking, structured retry, smart curation).

### GraphState with Annotated Merge
```python
# Artifacts use dict merge (operator.ior)
artifacts: Annotated[dict, operator.ior]

# Messages append
messages: Annotated[list, operator.add]
```
This prevents context collapse when parallel specialists write to state.

### Three Chat Modes
| Mode | Pattern | Use Case |
|------|---------|----------|
| CORE-CHAT-001 | Single ChatSpecialist | Simple queries |
| CORE-CHAT-002 | Parallel progenitors + formatted combination | Default |
| CORE-CHAT-003 | Parallel progenitors + DiplomaticSynthesizer + Arbiter loop | High-stakes |

---

## Safety Mechanisms

### Defense Against WGE (Whispering Gallery Effect)
- Context curation at specialist boundaries
- Explicit state management (no ambient context accumulation)
- Checkpoint-based conversation threading

### Defense Against RL-LMF
- Multi-model adversarial validation (Diplomatic Process)
- Different model providers for ProgenitorAlpha vs ProgenitorBravo
- Arbiter validates against Source of Truth, not engagement metrics

### Three-Stage Termination
Human control remains paramount through explicit termination sequence.

---

## MCP Integration

MCP provides synchronous service invocation between specialists, bypassing the router when direct communication is needed.

```python
# Service registration
registry.register("file_ops", FileSpecialist())

# Invocation with timeout protection
response = mcp_client.call_safe(
    service="file_ops",
    method="read",
    params={"path": "/data/input.json"},
    timeout_ms=5000
)
```

---

## Development Directives

### Script Discovery Protocol - CRITICAL
**ALWAYS check existing code before creating new solutions.**

1. Search `app/src/` for existing specialists/utilities
2. Check `docs/` for documented patterns
3. Review similar implementations in `tests/`
4. Only then create new code

### Workspace Directory - DO NOT USE
**NEVER look in `./workspace/` for existing code or write persistent application files there.**

- `./workspace/` is the Docker container's mounted root for LAS-scoped file operations
- It contains user data and runtime artifacts - NOT application source code
- Application code lives in `app/src/`, `app/tests/`, `docs/`, etc.

### ADR Symlink Structure (Private Docs)
`./docs/ADRs/` is a **symlink** to `../../design-docs/agentic-scaffold/03_ADRS/` (a separate private repo).

**Implications:**
- ADR files live in design-docs, NOT in this repo's git history
- **Never `git add` ADR files directly** - git will error on "beyond a symbolic link"
- ADR commits happen in design-docs repo separately
- When referencing ADRs in code comments, the symlink makes paths work locally

**When creating new ADRs:**
1. Check ALL subdirectories (completed/, implemented/, deferred/, PLANS/) for the highest sequence number
2. Check GitHub Issues (`gh issue list`) for ADR numbers reserved in issue descriptions (e.g., "pending ADR-040")
3. Create the file via the symlink path (`docs/ADRs/proposed/ADR-CORE-NNN.md`)
4. Commit in design-docs repo: `cd ~/github/shanevcantwell/design-docs && git add . && git commit`

### Statistical Anomalies
**NEVER dismiss statistical anomalies as coincidence.**

If parallel specialists produce suspiciously similar outputs:
- Calculate probability
- Flag as significant
- Investigate potential state leakage or model contamination

### Test Commit Atomicity
**When committing test changes, always update documentation atomically.**

1. Run `python scripts/summarize_tests.py` to regenerate `docs/generated/TEST_SUITE_SUMMARY.md`
2. Include the updated summary in the same commit as test file changes
3. This ensures documentation stays in sync with actual test coverage

---

## Git Operations Safety

### NEVER Use These Commands
```bash
git rm -rf .
git clean -fdx  # without explicit confirmation
git checkout --orphan <branch> && git rm -rf .
```

### SAFE Alternatives
```bash
git checkout HEAD -- .    # Restore tracked files
git stash                 # Save work safely
git reflog                # Find lost commits
```

### Critical Files to Preserve
- `*.code-workspace`
- `.vscode/`
- `.claude/`
- `pyproject.toml`

---

## Bug Tracking

Bugs are tracked via GitHub Issues. Use `gh` CLI for issue management.

### Creating Bug Issues
```bash
# Create a bug with full context
gh issue create \
  --title "BUG-XXX-NNN: Brief description" \
  --label "bug" \
  --body "## Summary\n..."

# List open bugs
gh issue list --label "bug"

# Reference issues in commits
git commit -m "Fix router context visibility (#3)"
```

### Bug Issue Structure
Every bug issue should include:
- **Summary**: One-sentence description
- **Reproduction**: Steps to trigger the bug
- **Evidence**: Failing test name, log output, or archive reference
- **Root Cause**: File and line number if known
- **Proposed Fix**: Code sketch or approach
- **Related**: Links to related issues or tests

### Test-First Bug Fixes
1. Write failing test that captures the bug behavior
2. Create GitHub Issue with test reference
3. Fix the code
4. Verify test passes
5. Close issue with commit reference

### Bug Naming Convention
`BUG-{AREA}-{NNN}`: e.g., `BUG-RESEARCH-001`, `BUG-ROUTER-002`

Areas: RESEARCH, ROUTER, MCP, STATE, TRIAGE, SPECIALIST

---

## Testing

### Philosophy: Integration Tests for LLM-Dependent Code

Anything that flows through Triage or Router requires **live models** to be meaningful. Mocked LLM responses don't validate real behavior—they just confirm the mock returns what you told it to return.

**Unit tests (mocks are valid):**
- Config parsing, schema validation, state merge logic
- Graph structure (nodes exist, edges connect)
- Procedural specialists (e.g., TieredSynthesizerSpecialist has no LLM)
- Post-LLM response handling (given a tool_call, test downstream parsing)
- Error paths (timeout handling, malformed response, missing artifacts)

**Integration tests (live models required):**
- Triage producing correct ContextPlan for queries
- Router selecting the right specialist
- Progenitors producing coherent responses
- End-to-end workflows

**The distinction:** Mock LLM responses to test *handling*, not to test *LLM behavior*.

### xfail Requires Human Approval - CRITICAL

**ALWAYS ask before marking tests as `xfail` or lowering test expectations.**

LLMs optimize toward "green" - we instinctively want to make tests pass. This creates a bias toward marking failures as "expected" rather than fixing underlying issues. When a test fails:

1. **First**: Understand why it's failing
2. **Second**: Propose options (fix the issue, adjust test, mark xfail)
3. **Third**: Ask the user which approach they prefer
4. **Never**: Unilaterally mark something xfail or change expected values to make tests pass

This applies to any change that lowers the bar: removing expected specialists, changing assertions to be more permissive, etc.

### Docker Required - CRITICAL

**Integration tests MUST run inside Docker.** The `.env` is configured for the proxy container—running from host fails for LMStudio/3090 connectivity.

**Container name:** `langgraph-app`

```bash
# Unit tests (from host)
pytest app/tests/unit/ -v

# Integration tests (inside Docker)
docker exec langgraph-app pytest -m integration

# All tests (inside Docker)
docker exec langgraph-app pytest

# Full suite with verbose output
docker exec langgraph-app pytest app/tests/ -v --tb=short
```

**NEVER use `docker compose run` for tests.** Always use `docker exec langgraph-app ...`
- `docker compose run` creates NEW containers that persist after completion
- Zombie containers accumulate and consume resources indefinitely
- If you see containers named `langgraph-agentic-scaffold-app-run-<hash>`, prune them: `docker container prune`

**Run tests in foreground without redirects.** Shell redirects (`>`, `2>&1`, `tee`) are unreliable in Claude Code's execution environment - output buffering causes lost results. Instead:
```bash
# Run directly in foreground - output streams reliably
docker exec langgraph-app pytest app/tests/integration/ -v --tb=short
```

Integration tests hit live LLMs and take 15+ minutes.

Never dismiss integration failures as "environmental" without confirming Docker context.

### Test Timeouts - CRITICAL

**Maximum test runtime: 15 minutes.** If tests run longer, something is wrong.

Typical turnaround times:
- Unit tests: ~15 seconds (21 tests)
- Single integration test: 30-90 seconds per LLM call
- Full integration suite: 10-15 minutes

If a test hangs, kill it and investigate. Don't wait indefinitely.

---

## Observability

### Archive System - PRIMARY DEBUG TOOL

**`./logs/archive/` contains the ground truth for what actually executed.**

Every workflow run produces a timestamped zip archive:
```
./logs/archive/run_YYYYMMDD_HHMMSS_<hash>.zip
```

Archive contents:
- `manifest.json` - routing_history, timestamps, run metadata
- `llm_traces.jsonl` - per-specialist execution with latency_ms
- `final_state.json` - accumulated state at workflow end
- `artifacts/` - all produced artifacts

**When debugging UI issues:**
1. Find the archive for the problematic run
2. Compare `routing_history` (what actually ran) vs UI display
3. Check `llm_traces.jsonl` for execution timing and errors

Example investigation:
```bash
# List recent archives
ls -la ./logs/archive/*.zip | tail -5

# Extract and inspect
unzip -l ./logs/archive/run_20260101_075556_4aa7cfa9.zip
unzip -p ./logs/archive/run_20260101_075556_4aa7cfa9.zip manifest.json | jq .
```

**The archive is authoritative.** If the UI shows something different from the archive, the bug is in the UI layer, not the execution layer.

---

## Specialist Development

### Creating a New Specialist
```python
from specialists.base import Specialist
from pydantic import BaseModel

class MySpecialistInput(BaseModel):
    query: str
    context: dict

class MySpecialistOutput(BaseModel):
    response: str
    confidence: float

class MySpecialist(Specialist):
    input_contract = MySpecialistInput
    output_contract = MySpecialistOutput
    
    async def execute(self, input_data: MySpecialistInput) -> MySpecialistOutput:
        # Implementation
        pass
```

### Specialist Constraints
- Always define Pydantic input/output contracts
- Never access GraphState directly; receive via dossier
- Return structured output; let SafeExecutor handle state updates
- Log at boundaries for debugging
