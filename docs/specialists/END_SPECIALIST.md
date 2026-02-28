# EndSpecialist Briefing: Graph Termination and Response Synthesis

**Purpose:** Technical briefing on EndSpecialist's role as graph terminator, response synthesizer, and archival coordinator.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-27

---

## Executive Summary

**EndSpecialist** is the **final convergence point** of the LAS orchestration graph. It runs immediately before `langgraph.END`, performing two critical functions:

1. **Response synthesis** — assembles a user-facing response from specialist outputs via LLM
2. **Archival coordination** — delegates to ArchiverSpecialist to produce a timestamped run archive

Key characteristics:
- **Three-tier priority waterfall** — termination reason > clarification questions > LLM synthesis
- **Hybrid type** — LLM-capable coordinator that internally owns procedural archival logic
- **Terminal node** — always routes to `langgraph.END`, never back into the graph
- **CORE_INFRASTRUCTURE member** — excluded from Router menu and hub-and-spoke edges
- **Atomic completion** — response synthesis and archival are a single coordinated operation

---

## Where EndSpecialist Fits in the Execution Flow

### Three Inbound Paths

```
1. Normal Completion
   Specialist → SignalProcessor → ExitInterview
       |
       [after_exit_interview]
       |-- COMPLETE ──────────────────────────────> EndSpecialist → END
       '-- INCOMPLETE + loop confirmed ──────────> EndSpecialist → END (with termination_reason)

2. Triage Rejection
   TriageArchitect
       |
       [check_triage_outcome]
       '-- ask_user-only ContextPlan ────────────> EndSpecialist → END (clarification questions)

3. SA Failure
   SystemsArchitect
       |
       [check_sa_outcome]
       '-- No task_plan produced ────────────────> EndSpecialist → END (with termination_reason)
```

### Single Outbound Edge

```
EndSpecialist → langgraph.END (unconditional)
```

EndSpecialist is a **terminal node**. No specialist routes back to it. It always terminates the workflow.

---

## Response Assembly Priority

EndSpecialist uses a **three-tier decision waterfall** in `_execute_logic()`. The first match wins.

### Tier 1: Explicit Termination Reason (Highest Priority)

```python
# end_specialist.py:104-106
if termination_reason:
    synthesized_response = termination_reason
```

**When triggered:** SA failure, loop detection + EI confirms incomplete, circuit breaker
**Effect:** Displays the system's own diagnosis directly — no LLM processing.

### Tier 2: Triage Clarification Questions

```python
# end_specialist.py:107-109
elif clarification_questions:
    synthesized_response = "I need some clarification before I can proceed:\n\n" + "\n".join(clarification_questions)
```

**When triggered:** Triage CLARIFY path — ContextPlan contains only `ask_user` actions (#179).
**Effect:** Formats triage questions as a bulleted list.

### Tier 3A: Pre-Existing Final Response (Skip LLM)

```python
# end_specialist.py:111-113
elif current_state.get("artifacts", {}).get("final_user_response.md"):
    synthesized_response = current_state["artifacts"]["final_user_response.md"]
```

**When triggered:** Another specialist already wrote `final_user_response.md` to artifacts.
**Effect:** Uses existing artifact directly, no synthesis needed.

### Tier 3B: LLM Synthesis from Snippets (Default Path)

```python
# end_specialist.py:114-117
else:
    synthesized_response = self._synthesize_response(current_state)
```

This is the normal path for completed workflows. See [Synthesis LLM Call](#synthesis-llm-call) below.

---

## Snippet Sourcing

EndSpecialist synthesizes from `scratchpad.user_response_snippets` — a list of strings written by specialists as they complete work.

### Who Writes Snippets

| Specialist | What It Writes | When |
|-----------|---------------|------|
| ChatSpecialist | Single conversational response | CORE-CHAT-001 simple queries |
| TieredSynthesizerSpecialist | Combined progenitor output | CORE-CHAT-002 parallel chat |
| DefaultResponderSpecialist | Greeting/small talk response | Trivial requests |

### Who Does NOT Write Snippets

| Specialist | Why Not | Where Output Goes |
|-----------|---------|-------------------|
| ProjectDirector | Action-oriented (file ops, web research) | `messages[0]` (AIMessage with final_response) |
| WebBuilder | Builds artifacts (HTML, Gradio apps) | Artifacts + messages |
| ExitInterview | Validation gate, not content producer | `exit_interview_result` artifact |

When no snippets exist (e.g., PD completed a task), EndSpecialist falls back to reading the last message from `state.messages`.

---

## Synthesis LLM Call

### Prompt

**File:** `app/prompts/response_synthesizer_prompt.md`

> You are a helpful assistant whose sole purpose is to synthesize a final, coherent, and user-friendly response from a collection of information snippets.
>
> Following are snippets from other agents in the workflow. They represent those agents' attempts to speak directly to the user. Synthesize the snippets carefully to be succinct without losing any semantic meaning contained in any and all of the snippets. Create a single, well-structured, and easy-to-understand message for the user. Ensure the tone is helpful and professional. Do not fictionalize, add unasked information, or include any new information that was not present in the snippets.

### Key Constraints
- **No hallucination** — only synthesize, never add information
- **Semantic preservation** — all snippet content must appear in the output
- **Succinct** — compress without loss

### Fallback When No Snippets Exist

```python
# end_specialist.py:54-64
if not user_response_snippets:
    last_message = messages[-1]
    if isinstance(last_message, ToolMessage):
        return f"The task finished with the following result:\n\n```\n{last_message.content}\n```"
    elif isinstance(last_message, AIMessage) and last_message.content:
        return last_message.content
    else:
        return "The workflow has completed its tasks, but no specific output was generated to display."
```

---

## Termination Reason Sources

### SA Failure (`check_sa_outcome`)

```python
# graph_orchestrator.py:88-98
scratchpad["termination_reason"] = f"Planning failed: {sa_error}\n\nThe Systems Architect could not produce a valid task plan..."
```

**Triggered when:** SystemsArchitect fails to produce `task_plan` (validation failure, LLM error).

### Loop Detection + EI Incomplete (`after_exit_interview`)

```python
# graph_orchestrator.py:400-415
scratchpad["termination_reason"] = (
    f"The workflow is stuck in an unproductive loop and has been halted. "
    f"The sequence '{sequence}' was repeated {cycles} times, "
    f"and Exit Interview confirmed the task is incomplete."
)
```

**Triggered when:** `_is_unproductive_loop()` detects a repeating routing pattern AND ExitInterview validates that the task is still incomplete.

---

## Archival Integration

EndSpecialist delegates archival to an internally-instantiated ArchiverSpecialist.

```python
# end_specialist.py:132-136
archival_updates = self.archiver._execute_logic(current_state)
return archival_updates
```

**Note:** EndSpecialist returns the *archiver's* state updates, not its own. The archiver's updates include the synthesized response (already written to `current_state.artifacts["final_user_response.md"]` before archival).

### Archive Contents

| File | Contents |
|------|----------|
| `manifest.json` | routing_history, timestamps, run metadata |
| `report.md` | Human-readable summary with artifacts and routing |
| `llm_traces.jsonl` | Per-specialist LLM prompts and responses |
| `final_state.json` | Accumulated state at workflow end |
| `artifacts/` | All produced artifacts |

### Archive Configuration

```yaml
# config.yaml:481-491
end_specialist:
  type: "hybrid"
  synthesis_prompt_file: "response_synthesizer_prompt.md"
  archiver_config:
    type: "procedural"
    archive_path: "./logs/archive"
    pruning_strategy: "count"   # "count" or "none"
    pruning_max_count: 0        # 0 = disable pruning
```

---

## State I/O

### Reads

| Source | Field | Purpose |
|--------|-------|---------|
| `scratchpad` | `termination_reason` | Abort/error message (Tier 1) |
| `scratchpad` | `triage_actions` | Clarification questions (Tier 2) |
| `scratchpad` | `user_response_snippets` | Specialist outputs for synthesis (Tier 3B) |
| `artifacts` | `final_user_response.md` | Pre-existing response (Tier 3A) |
| `messages` | Last message | Fallback when no snippets |

### Writes

| Target | Field | Value |
|--------|-------|-------|
| `artifacts` | `final_user_response.md` | Synthesized/selected response text |
| `messages` | Appended AIMessage | Response with `synthesized_from_snippets: True` |
| `scratchpad` | `user_response_snippets` | Cleared to `[]` (consumed) |

---

## Graph Wiring

### Inbound Edges

| Source | Edge Function | Condition | File |
|--------|---------------|-----------|------|
| TriageArchitect | `check_triage_outcome` | ask_user-only ContextPlan | graph_orchestrator.py:53-55 |
| SystemsArchitect | `check_sa_outcome` | No task_plan produced | graph_orchestrator.py:96-98 |
| ExitInterview | `after_exit_interview` | COMPLETE, or INCOMPLETE + loop confirmed | graph_orchestrator.py:395-415 |
| check_task_completion | (multiple paths) | EI-validated completion, SKIP_EI specialists, parallel barrier | graph_orchestrator.py:132-172 |

### Outbound Edge

```python
# graph_builder.py:619-620
workflow.add_edge(end_specialist_name, END)
```

Unconditional edge to `langgraph.END`.

---

## Archive Forensics

### Debugging Final Response Issues

```bash
# What response was shown to the user?
unzip -p $ARCHIVE report.md | head -20

# Was it synthesized or a termination reason?
unzip -p $ARCHIVE final_state.json | jq '.artifacts["final_user_response.md"]' | head -5

# Was there a termination reason?
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.termination_reason'

# What snippets were available for synthesis?
# (Will be [] after EndSpecialist clears them, check state_timeline for pre-clear state)
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.user_response_snippets'

# Check EndSpecialist's LLM trace (only present on Tier 3B synthesis path)
python scripts/analyze_archive.py $ARCHIVE traces | grep end_specialist
```

### Common Issues

| Symptom | Check | Root Cause |
|---------|-------|------------|
| Generic "workflow completed" message | `user_response_snippets` empty, last message not AIMessage | Action specialist (PD) completed but no conversational specialist formatted the output |
| Termination message instead of result | `scratchpad.termination_reason` | Loop detected + EI incomplete, or SA failure |
| Truncated or incomplete response | Synthesis prompt output | LLM cut off during synthesis (check model max_tokens) |
| Duplicate content in response | Multiple snippet sources | Multiple specialists wrote snippets in same workflow |

---

## What EndSpecialist Does NOT Do

| Capability | EndSpecialist | Who Does It |
|------------|--------------|-------------|
| Route requests | No | Router |
| Assemble context | No | Facilitator |
| Validate task completion | No | ExitInterview |
| Execute tasks | No | PD, WebBuilder, etc. |
| Produce research or artifacts | No | Specialists |
| Decide whether to retry | No | after_exit_interview edge function |

---

## Key Files

| File | Purpose |
|------|---------|
| [end_specialist.py](../../app/src/specialists/end_specialist.py) | Implementation: synthesis waterfall, archival coordination |
| [response_synthesizer_prompt.md](../../app/prompts/response_synthesizer_prompt.md) | LLM prompt for snippet synthesis |
| [archiver_specialist.py](../../app/src/specialists/archiver_specialist.py) | Archive production (instantiated by EndSpecialist) |
| [config.yaml](../../config.yaml) | EndSpecialist config: synthesis_prompt_file, archiver_config |
| [graph_builder.py](../../app/src/workflow/graph_builder.py) | Adapter attachment, node registration, `→ END` edge |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | Inbound edge functions: check_triage_outcome, check_sa_outcome, after_exit_interview, check_task_completion |
| [specialist_categories.py](../../app/src/workflow/specialist_categories.py) | CORE_INFRASTRUCTURE membership |

---

## Summary

EndSpecialist is the **graph terminator** that:

1. Applies a three-tier priority waterfall: termination reason > clarification questions > LLM synthesis from snippets
2. Synthesizes diverse specialist outputs into a single coherent response via LLM (no hallucination, semantic preservation)
3. Falls back gracefully when no snippets exist (reads last message, or generates generic completion)
4. Coordinates atomic archival via internally-instantiated ArchiverSpecialist
5. Is the last specialist to touch the user's response — debugging "why does the output look wrong" starts here

EndSpecialist answers **"what should the user see?"** It does not answer **"who should do the work?"** (Router), **"what context do they need?"** (Facilitator), or **"is the work done?"** (ExitInterview).
