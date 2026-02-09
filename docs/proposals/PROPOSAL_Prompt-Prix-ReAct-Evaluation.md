# Feature Proposal: ReAct Loop Evaluation in prompt-prix

**From:** LAS (langgraph-agentic-scaffold)
**To:** prompt-prix
**Date:** 2026-02-06
**Status:** Proposal

## Problem

prompt-prix currently tests single-shot prompting: one prompt in, one response out, judge
the response. This works for classification and generation tasks but misses the primary
failure mode we observe in production: **model degradation over iterative ReAct execution**.

### What we see in production

LAS's `ProjectDirector` runs a ReAct loop (`execute_with_tools`) where the model
iteratively calls MCP tools (list_directory, read_file, move_file, create_directory,
run_command) and sees the results. The loop rebuilds the full message history from a
canonical trace each iteration — so by iteration 10, the model is seeing:

```
HumanMessage(goal)
AIMessage(tool_calls=[list_directory("./sort_test")])
ToolMessage("[FILE] 1.txt\n[FILE] 2.txt\n...")
AIMessage(tool_calls=[read_file("./sort_test/1.txt")])
ToolMessage("The zebra is a striped animal...")
AIMessage(tool_calls=[create_directory("./sort_test/animals")])
ToolMessage("Directory created")
AIMessage(tool_calls=[move_file("./sort_test/1.txt", "./sort_test/animals/1.txt")])
ToolMessage("File moved")
... (6-8 more rounds)
```

**Models that ace the single-shot eval degrade in this loop.** Specific failure observed
with gpt-oss-20b at iteration 9:

```
[iter 9]  create_directory(path='./categories?2?0??')   # garbled path
[iter 10] create_directory(path='./categories_test/colors')  # recovered
[iter 11] move_file(source='', destination='')            # empty args
[iter 12] run_command(command='')                         # empty
```

The model produces correct single-shot plans 10/10 times, but falls apart after 8+
iterations of accumulated context. Our current eval (file_categorization_eval.yaml)
can't detect this because it only tests the planning phase.

### The eval gap

| What we test now | What breaks in production |
|---|---|
| "Here are 6 files and 3 folders, produce a JSON plan" | "Here's file 1 content: zebra. You just created animals/. Now move 1.txt there." (repeat 12x) |
| Single prompt → single response | 10-15 round-trip iterations with growing context |
| All information upfront | Information revealed progressively via tool results |
| Clean JSON schema adherence | Schema coherence under context window pressure |

## What prompt-prix Needs

### 1. Multi-turn conversation mode

A test spec that defines a **sequence** of prompt/response rounds, not just one:

```yaml
tests:
  - description: "File categorization via ReAct (6 files)"
    mode: react  # NEW: indicates multi-turn evaluation
    turns:
      - prompt: "List the directory"
        # Simulated tool response (what MCP would return)
        mock_tool_result: "[FILE] 1.txt\n[FILE] 2.txt\n[FILE] 3.txt\n..."
      - prompt: null  # Continue from model's previous response
        mock_tool_result: "The zebra is a striped animal native to Africa."
      # ... model drives the conversation, prompt-prix provides mock tool results
```

The key insight: **the model drives the loop, prompt-prix provides mock tool results**.
This simulates the ReAct execution without requiring a live filesystem.

### 2. Accumulated context tracking

prompt-prix needs to maintain conversation state across turns:
- Message history grows with each round (model sees its own prior tool calls + results)
- The format must match what LAS's `_serialize_for_provider()` produces:
  - `HumanMessage` → goal prompt
  - `AIMessage` with `tool_calls` → model's tool selection
  - `ToolMessage` → mock tool result

This is the "context accumulation" that makes ReAct hard to eval — the model doesn't
just see the current turn, it sees everything it's done so far.

### 3. Progressive assertion

Single-shot evals assert on the final response. ReAct evals need to assert on the
**trajectory**:

- **Per-turn assertions**: Did the model call the right tool with valid args at step N?
- **Degradation detection**: Did arg quality decline over iterations? (e.g., paths went
  from valid to garbled)
- **Completion assertions**: Did the model finish all operations before hitting max_iterations?
- **Schema coherence**: Are tool call args still well-formed at iteration 10?

```yaml
assert:
  # Final state check
  - type: trajectory
    value: |
      // All 6 files should have been moved
      const moves = trajectory.filter(t => t.tool === 'move_file' && t.success);
      return moves.length === 6;

  # Degradation check
  - type: trajectory
    value: |
      // No empty args in any tool call
      return trajectory.every(t => {
        const args = Object.values(t.args);
        return args.length > 0 && args.every(a => a.length > 0);
      });
```

### 4. Mock tool response mapping

prompt-prix needs a way to define deterministic mock responses for tool calls, so evals
are reproducible:

```yaml
mock_tools:
  list_directory:
    "./sort_test":
      response: "[FILE] 1.txt\n[FILE] 2.txt\n[FILE] 3.txt\n[DIR] animals/\n[DIR] fruits/\n[DIR] colors/"
  read_file:
    "./sort_test/1.txt":
      response: "The zebra is a striped animal native to Africa."
    "./sort_test/2.txt":
      response: "An apple is a delicious fruit that grows on trees."
  create_directory:
    _default:
      response: "Directory created"
  move_file:
    _default:
      response: "File moved"
```

This makes ReAct evals deterministic — same mock tools, same expected trajectory —
while testing the model's ability to maintain coherence over iterations.

### 5. LMStudio adapter parallel fan-out

The existing LMStudio adapter dispatches to one model at a time. For ReAct evals, we need
to run the same multi-turn scenario against N models in parallel. This means:

- N concurrent conversation states (one per model)
- Each model gets the same mock tool responses
- Fan-out at the conversation level, not the single-request level
- Results collected per-model for comparison

This is different from the current consistency run (N identical single-shot requests) —
it's N parallel multi-turn conversations.

## Ground Truth for File Categorization ReAct

The mock tool responses and expected trajectories for the file categorization task:

**Setup**: 6 files in `./sort_test/`, 3 target folders (animals/, fruits/, colors/)

**Expected trajectory** (order may vary, operations must all complete):
1. `list_directory("./sort_test")` → see files and folders
2. `read_file` × 6 → read each file's content
3. `move_file` × 6 → move each to correct folder

**Ground truth moves:**
| File | Content signal | Expected destination |
|---|---|---|
| 1.txt | zebra | animals/ |
| 2.txt | apple | fruits/ |
| 3.txt | blue sky | colors/ |
| 4.txt | elephants | animals/ |
| 5.txt | bananas | fruits/ |
| 6.txt | red (color) | colors/ |

**What we're actually testing**: Not whether the model knows zebra=animal (single-shot
proves that), but whether it can execute 15+ tool calls without degenerating.

## Integration Points

### semantic-chunker MCP

For non-deterministic aspects of evaluation (rationale quality, response coherence),
prompt-prix can use semantic-chunker's tools:

- `calculate_drift` — measure cosine distance between a model's early vs late responses
  to detect quality degradation
- `classify_document` — DMA-mode classification of response quality without loading to
  LLM judge context

### LAS archive format

LAS already captures full ReAct traces in `logs/archive/*.zip` as `research_trace_N`
artifacts. prompt-prix could ingest these as "replay" scenarios — use real production
traces as the mock tool response sequence, testing whether a different model would have
done better with the same observations.

## Relation to Current Results

Our file_categorization_eval (single-shot, 10x consistency, 9 models) found:
- **3 models at 100%**: qwen3-30b-a3b, gpt-oss-20b, nemotron-3-nano
- **gemma-12b judge wrong on 14/36 cells** (false passes for truncated/malformed responses)

But gpt-oss-20b, despite 100% on single-shot planning, produces garbled output by
iteration 9 in production ReAct. **The single-shot eval is necessary but not sufficient.**

The ReAct eval would catch this: gpt-oss-20b would pass the planning phase but fail the
execution trajectory check when its args degenerate mid-loop.

## Summary

| Capability | Current prompt-prix | Needed for ReAct eval |
|---|---|---|
| Single prompt/response | Yes | Yes (still needed) |
| Multi-turn conversation | No | Yes |
| Mock tool responses | No | Yes |
| Trajectory assertions | No | Yes |
| Conversation-level fan-out | No | Yes (parallel models) |
| Degradation detection | No | Yes |
| Archive replay | No | Nice-to-have |

---

## Appendix: LAS Reference Assets

Code and data from LAS that prompt-prix can directly use or reference when implementing
ReAct evaluation. Paths are relative to the LAS repo root.

### Reusable Code (zero LAS dependencies)

**Cycle detection algorithm** — `app/src/resilience/cycle_detection.py`
- `detect_cycle_with_pattern(signatures, min_repetitions)` → `(period, pattern) | (None, None)`
- Self-contained, no imports beyond stdlib. Detects both identical repetition (A-A-A)
  and cyclic patterns (A-B-C-A-B-C). Returns the period length and repeating pattern.
- prompt-prix can drop this in directly for trajectory quality analysis.

**Tool parameter registry** — `app/src/specialists/mixins/react_mixin.py:288-318`
- `TOOL_PARAMETERS` dict maps tool name → `{param_name: (type, Field(...))}`.
- Defines every tool's typed signature: `list_directory(path)`, `read_file(path)`,
  `move_file(source, destination)`, `create_directory(path)`, `run_command(command)`, etc.
- This IS the mock tool interface spec. prompt-prix's mock_tools should accept/validate
  the same parameter shapes.

### Reference Implementations

**LMStudio adapter — tool schema construction** — `app/src/llm/lmstudio_adapter.py:96-169`
- `_build_tool_call_schema()` constructs a draft-07 JSON schema for structured tool calling.
  Merges all tool parameters into a single schema with `reasoning`, `action` (containing
  `tool_name` enum + per-tool params), and `final_response` fields.
- Adds `DONE` pseudo-tool only for multi-tool scenarios (ReAct). Single-tool specialists
  don't get it (#138).
- prompt-prix already has its own adapter but needs this specific schema shape for ReAct
  evals — it's what models see in production.

**LMStudio adapter — response parsing** — `app/src/llm/lmstudio_adapter.py:428-482`
- Extracts tool calls from JSON-schema-enforced responses. Handles nested
  (`{"action": {"tool_name": ...}}`) and flat formats. Detects task completion via `DONE`.
- Shows the format variation prompt-prix needs to handle when parsing model responses
  during multi-turn eval.

**Message serialization** — `app/src/specialists/mixins/react_mixin.py:648-696`
- `_serialize_for_provider(goal, trace)` rebuilds LangChain messages from canonical trace.
- ~50 lines that define exactly how accumulated context looks to a model at iteration N.
- This is the single most important piece for prompt-prix to replicate. Without matching
  this serialization, prompt-prix would test a different context shape than production.

**Error enrichment** — `app/src/specialists/mixins/react_mixin.py:61-137`
- `_enrich_filesystem_error()` adds recovery hints to ENOENT errors.
- `_enrich_list_directory_result()` prepends directory paths to entries
  (`[FILE] c.txt` → `[FILE] sort_by_contents/c.txt`).
- prompt-prix's mock tool responses should match this enriched format, not raw MCP output,
  since that's what models actually see during production ReAct.

### Trace Data

**Production archives** — `logs/archive/*.zip`
- Real ReAct traces from real runs, including the gpt-oss-20b degradation case.
- Each ZIP contains `manifest.json` (routing_history, metadata), `llm_traces.jsonl`
  (per-specialist SpecialistTurnTrace with model_id, tool_calls, latency_ms, assembled_prompt),
  and serialized artifacts.
- Can be replayed as mock tool response sequences: "given these observations, would
  model X have done better?"

**Trace schema** — `app/src/llm/tracing.py:40-74`
- `SpecialistTurnTrace`: system_prompt, assembled_prompt, response_text, tool_calls,
  artifacts_produced, routing_decision, latency_ms, model_id.
- This is the format prompt-prix would parse from archives for replay scenarios.

**Serialized ReAct iterations** — `app/src/specialists/project_director.py:407-422`
- `_serialize_react_iteration()` produces the dict stored in archives:
  `{iteration, tool, args, success, thought, observation_preview}`.
- prompt-prix can deserialize these to reconstruct the exact tool call sequence
  a model produced in production.

### Config Shape

**ReAct specialist config** — `config.yaml:341-347` (example)
```yaml
react:
  enabled: true
  max_iterations: 15
tools:
  filesystem: [list_directory, read_file, create_directory, move_file]
  terminal: [run_command]
```
- Shows which tools are available per specialist and iteration limits.
- prompt-prix can use this to validate tool usage scope in trajectory assertions.

### State Merging Semantics

**GraphState** — `app/src/graph/state.py`
- `artifacts: Annotated[dict, operator.ior]` — dict merge (not overwrite)
- `messages: Annotated[list, operator.add]` — list append
- `llm_traces: Annotated[List[Dict], operator.add]` — list append
- Relevant if prompt-prix ever needs to understand how parallel specialist outputs
  combine without clobbering each other.
