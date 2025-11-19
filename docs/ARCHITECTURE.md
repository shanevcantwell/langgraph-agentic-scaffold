# System Architecture

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

## 2.0 System Architecture

The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task.
2.  **Runtime Orchestrator (`RouterSpecialist` & `GraphOrchestrator`):** The `RouterSpecialist` is an agent that makes the turn-by-turn routing decisions *within* the graph. The `GraphOrchestrator` contains the runtime logic (decider functions, safety wrappers) that the graph itself executes.
3.  **Structural Orchestrator (`GraphBuilder`):** A high-level system component responsible for building the `LangGraph` instance and enforcing global rules.

The system also includes a robust set of custom exceptions (e.g., `ProxyError`, `SafetyFilterError`, `RateLimitError`) to provide clear, actionable error messages instead of generic failures, which is critical for debugging agentic workflows.

## 2.1 BREAKING CHANGE: State Purge (Nov 14, 2025)

**Task 2.7 Migration:** Deprecated specialist-specific fields have been removed from root `GraphState` and migrated to `scratchpad` to enforce architectural purity (ADR-CORE-004).

### What Changed

The following fields have been **REMOVED** from root GraphState:
- `Dossier` TypedDict (obsolete - superseded by MCP)
- `text_to_process` in Artifacts model (redundant - use artifacts dict directly)
- `recommended_specialists` at root level → **moved to scratchpad**
- `error_report` at root level → **moved to scratchpad**

### Migration Pattern

```python
# ❌ OLD (before Task 2.7)
def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
    # Read
    next_specialist = state.get("recommended_specialists")
    error = state.get("error_report")

    # Write
    return {
        "recommended_specialists": ["file_specialist"],
        "error_report": "Something failed"
    }

# ✅ NEW (after Task 2.7)
def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
    # Read
    scratchpad = state.get("scratchpad", {})
    next_specialist = scratchpad.get("recommended_specialists")
    error = scratchpad.get("error_report")

    # Write
    return {
        "scratchpad": {
            "recommended_specialists": ["file_specialist"],
            "error_report": "Something failed"
        }
    }
```

### Rationale

**Architectural Purity (ADR-CORE-004):**
- Root GraphState = core orchestration only (messages, routing_history, turn_count, etc.)
- Scratchpad = transient specialist communication signals
- Moving `recommended_specialists` and `error_report` to scratchpad enforces proper state management hygiene

**Dossier Obsolescence:**
- The Dossier pattern (ADR-CORE-003) has been **superseded by MCP** (ADR-CORE-008)
- Use `McpClient` for synchronous service calls instead of async Dossier handoffs
- Direct edges + artifacts pattern for workflow handoffs (ADR-CORE-012)

### Impact

- **Breaking Change:** All code accessing these fields must update to scratchpad pattern
- **Test Coverage:** 440+ tests passing with new structure
- **Documentation:** See commits `2adcf94`, `d40f43f`, `e011646` for complete migration

## 3.0 Architectural Best Practices & Lessons Learned

### 3.1 Principle: Match Model Capability to Architectural Role

The `router_specialist` is the most critical reasoning component in the architecture. Assigning a small or less capable model to this role is a significant architectural risk and has been observed to cause pathological failures (runaway generation, context collapse).

**Recommendation:** The `router_specialist` should be run by a capable, instruction-tuned model known for reliable tool use (e.g., Gemini Flash, GPT-3.5-Turbo, or larger). Reserve smaller, more efficient models for more constrained, less critical specialist tasks.

### 3.2 Pattern: Intentional vs. Unproductive Loops

The `GraphOrchestrator` includes a generic loop detection mechanism to halt unproductive cycles (e.g., a sequence like `Router -> Specialist A -> Router -> Specialist A ...`). This mechanism inspects the `routing_history` to prevent the system from getting stuck. This is the preferred pattern for creating controlled, stateful cycles.

Intentional loops, such as the "Generate-and-Critique" cycle, are architected differently. They are implemented using conditional edges in the graph that create a direct `Specialist A -> Specialist B -> Specialist A` sub-graph. Because this sub-loop does not repeatedly pass through the main `RouterSpecialist`, it is not flagged by the generic unproductive loop detector. This is the preferred pattern for creating controlled, stateful cycles.

### 3.3 Contract: The Adapter Robust Parsing Contract

**Principle:** The LLM Adapter layer is solely responsible for abstracting provider-specific idiosyncrasies. This includes inconsistent formatting of structured data responses.

**Policy:** All concrete implementations of `BaseAdapter` MUST adhere to the Robust Parsing Contract. When a specialist requests structured data (e.g., via `output_model_class`), the adapter is responsible for returning a valid, parsed JSON object if one can be reasonably extracted from the provider's raw response.

**Implementation:** To ensure consistency and prevent code duplication, all adapters MUST utilize the `_robustly_parse_json_from_text()` helper method provided by the `BaseAdapter` class as a fallback mechanism. An adapter should only return an empty `json_response` if both a direct parse and the robust fallback parse fail. This contract is non-negotiable and is verified by the system's contract tests (`app/tests/llm/test_adapter_contracts.py`).

### 3.4 Pattern: Enforce Centralized Control with Coordinated Completion Sequence

To ensure system stability and predictable behavior, this architecture employs a mandatory **completion sequence**. Functional specialists are forbidden from terminating the graph directly. Instead, they signal task completion or produce final artifacts, which triggers a standardized shutdown process.

This pattern is critical for ensuring that final housekeeping tasks, such as synthesizing a user-friendly response and generating an archive report, are always executed. The completion of the workflow is a deliberate, centralized, and observable event.

The process is as follows:

1.  **Stage 1: Signal Completion**
    *   A functional specialist (e.g., `critic_specialist` after accepting work) completes its primary task.
    *   It signals this by including `task_is_complete: True` in its return state.
    *   The `GraphBuilder` configures a conditional edge that checks for the `task_is_complete` flag. When this flag is `True`, graph execution is routed to the `end_specialist` instead of back to the main `router_specialist`.

2.  **Stage 2: Coordinate Finalization (`EndSpecialist`)**
    *   The `end_specialist`, a hybrid coordinator, is invoked. It uses an LLM for response synthesis and procedural logic for archiving.
    *   As a unified coordinator, it performs finalization atomically:
        1.  **Synthesis:** It synthesizes the `final_user_response.md` artifact from any accumulated `user_response_snippets` using its LLM adapter. If no snippets are found, it intelligently uses the content of the last conversational AI message as the source for the final response.
        2.  **Archiving:** It then immediately generates the final `archive_report.md` by invoking its internal archiver component, passing it the complete, updated state (including the newly synthesized response).

3.  **Stage 3: Confirm Completion**
    *   After the `end_specialist` completes, the `archive_report.md` artifact exists in the state.
    *   On the next turn, the `RouterSpecialist` performs a pre-LLM check. It sees the `archive_report.md` artifact and deterministically routes to the special `END` node, cleanly completing the graph execution.

This explicit, coordinated sequence ensures that completion is a robust, observable process, centralizing the finalization logic and preventing premature or disorderly graph exits.

### 3.5 Pattern: Hybrid Specialist Configuration (Open Interpreter)

**Context:** Some specialists, like `OpenInterpreterSpecialist`, rely on external libraries (`open-interpreter`) that have their own internal LLM handling logic. This can lead to configuration drift where the library tries to use default settings (e.g., OpenAI GPT-4) instead of the application's configured LLM.

**Solution:** The specialist implementation must explicitly bridge the application's `LLMAdapter` configuration to the external library's configuration at runtime.

**Implementation:**
In `OpenInterpreterSpecialist._execute_code`, we explicitly inject the adapter's settings into the interpreter instance before execution:

```python
if self.llm_adapter:
    interpreter.llm.api_base = self.llm_adapter.api_base
    interpreter.llm.api_key = self.llm_adapter.api_key or "not-needed"
    interpreter.llm.model = self.llm_adapter.model_name or "openai/gpt-4-turbo"
    interpreter.llm.max_tokens = getattr(self.llm_adapter, 'max_tokens', 4096)
```

This ensures that `open-interpreter` respects the local model bindings defined in `user_settings.yaml` (e.g., `lmstudio_specialist`), preventing accidental API calls to cloud providers when local execution is intended.

## 4.0 Pattern: Virtual Coordinator with Parallel Execution (CORE-CHAT-002)

The Virtual Coordinator pattern enables the system to transparently upgrade single-node capabilities into multi-node subgraphs without exposing implementation details to the router. This pattern is exemplified by the **Tiered Chat Subgraph**, which transforms a single chat specialist into a parallel multi-perspective system.

### 4.1 Architectural Overview

**Semantic Separation:**
- **Router's Perspective:** "The user needs chat capability" → routes to `"chat_specialist"`
- **Orchestrator's Perspective:** "How do we provide chat?" → intercepts and fans out to parallel progenitors
- **Separation of Concerns:** Router decides WHAT (capability), Orchestrator decides HOW (implementation)

**Graph Structure When Tiered Chat Enabled:**

```
User Query
    ↓
RouterSpecialist (chooses "chat_specialist")
    ↓
GraphOrchestrator.route_to_next_specialist() [INTERCEPTION POINT]
    ↓
    ├─→ ProgenitorAlphaSpecialist (Analytical perspective)
    │
    └─→ ProgenitorBravoSpecialist (Contextual perspective)

    [Parallel execution - both run simultaneously]

         ↓                    ↓
         └────────┬───────────┘
                  ↓
    TieredSynthesizerSpecialist (combines both)
                  ↓
          Check task completion
                  ↓
            EndSpecialist
                  ↓
               END node
```

### 4.2 Critical State Management Pattern

**CRITICAL:** Progenitor specialists (parallel nodes) must write ONLY to `artifacts`, never to `messages`:

```python
# ProgenitorAlphaSpecialist - CORRECT
def _execute_logic(self, state: dict) -> dict:
    # ... LLM call generates response ...

    # CRITICAL: Write to artifacts only, NOT to messages
    return {
        "artifacts": {
            "alpha_response": ai_response_content
        }
        # NO "messages" key!
    }

# TieredSynthesizerSpecialist - JOIN NODE
def _execute_logic(self, state: dict) -> dict:
    # Join node reads artifacts and writes to messages
    alpha = state["artifacts"]["alpha_response"]
    bravo = state["artifacts"]["bravo_response"]
    combined = format_both(alpha, bravo)

    return {
        "messages": [create_llm_message(..., combined)],
        "artifacts": {"final_user_response.md": combined},
        "task_is_complete": True
    }
```

**Why This Matters:**

In LangGraph's fan-out/join pattern:
- **Parallel nodes (fan-out):** Write to temporary storage (`artifacts`)
- **Join node (fan-in):** Reads artifacts and writes to permanent storage (`messages`)

This prevents message pollution and enables proper multi-turn conversation cross-referencing. Without this pattern, multi-turn conversations would accumulate 4 messages per turn (user, alpha, bravo, synthesizer) instead of 2 (user, synthesizer), causing:
- 78% token waste (~1600 vs ~900 tokens per turn)
- Broken cross-referencing (progenitors can't reference each other's past responses)
- Context pollution in conversation history

### 4.3 Implementation Details

**Orchestrator Interception (`GraphOrchestrator.route_to_next_specialist()`):**

```python
def route_to_next_specialist(self, state: GraphState) -> str | list[str]:
    """
    Routes from RouterSpecialist to the next specialist(s).

    Can return either:
    - A single specialist name (str) for normal routing
    - A list of specialist names (list[str]) for parallel fan-out execution
    """
    next_specialist = state.get("next_specialist")

    # CORE-CHAT-002: Intercept chat_specialist routing
    if next_specialist == "chat_specialist":
        if self._has_tiered_chat_specialists():
            logger.info("Chat routing detected - fanning out to parallel progenitors")
            return ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]

    return next_specialist
```

**Graph Wiring (Fan-In Pattern):**

```python
# CRITICAL: Use array syntax for proper fan-in (join node)
workflow.add_edge(
    ["progenitor_alpha_specialist", "progenitor_bravo_specialist"],
    "tiered_synthesizer_specialist"
)
```

The array syntax `["node_a", "node_b"]` is essential - it tells LangGraph that the synthesizer node should wait for BOTH predecessors to complete before executing. Without this, the synthesizer would execute twice (once per predecessor).

### 4.4 Graceful Degradation Strategy (CORE-CHAT-002.1)

The TieredSynthesizerSpecialist implements graceful degradation to handle partial failures:

**Response Modes:**
- `"tiered_full"` - Both progenitors responded successfully (happy path)
- `"tiered_alpha_only"` - Only ProgenitorAlpha succeeded (Bravo failed)
- `"tiered_bravo_only"` - Only ProgenitorBravo succeeded (Alpha failed)
- `"error"` - Complete failure (neither progenitor responded)

**Implementation:**

```python
alpha_response = state.get("artifacts", {}).get("alpha_response")
bravo_response = state.get("artifacts", {}).get("bravo_response")

if alpha_response and bravo_response:
    response_mode = "tiered_full"
    output = format_both_perspectives(alpha_response, bravo_response)
elif alpha_response:
    response_mode = "tiered_alpha_only"
    output = format_single_perspective("Analytical View", alpha_response)
    logger.warning("Degraded mode: Bravo perspective unavailable")
elif bravo_response:
    response_mode = "tiered_bravo_only"
    output = format_single_perspective("Contextual View", bravo_response)
    logger.warning("Degraded mode: Alpha perspective unavailable")
else:
    raise ValueError("No progenitor responses available")
```

### 4.5 Efficiency Optimization: Skip Redundant Synthesis

The TieredSynthesizerSpecialist writes to `artifacts.final_user_response.md` to prevent the EndSpecialist from performing a redundant LLM synthesis call:

```python
return {
    "messages": [ai_message],
    "artifacts": {
        "response_mode": response_mode,
        "final_user_response.md": tiered_response  # Skip EndSpecialist synthesis
    },
    "scratchpad": {
        "user_response_snippets": [tiered_response]
    },
    "task_is_complete": True
}
```

This optimization reduces LLM calls from 3 (Alpha + Bravo + EndSynthesis) to 2 (Alpha + Bravo only).

### 4.6 Model Binding Configuration

The tiered chat architecture is **model-agnostic**. Concrete model bindings are runtime configuration:

**Development (zero API cost):**
```yaml
# user_settings.yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "lmstudio_specialist"
  progenitor_bravo_specialist: "lmstudio_specialist"
```

**Hybrid (mixed cost/quality):**
```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "gemini_pro"
  progenitor_bravo_specialist: "lmstudio_specialist"
```

**Production (PAYG):**
```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "gemini_pro"
  progenitor_bravo_specialist: "claude_sonnet"
```

### 4.7 Observability

**Logging:**
- INFO level when interception occurs: "Chat routing detected - fanning out to parallel progenitors"
- WARNING level for degraded modes with failure reasons
- Structured logging includes `routing_mode` and `response_mode`

**LangSmith Traces:**
- `routing_history` shows: `["router_specialist", "progenitor_alpha_specialist", "progenitor_bravo_specialist", "tiered_synthesizer_specialist"]`
- Parallel execution visible in trace timeline (both progenitors run simultaneously)
- Each specialist's message shows execution status

**Archive Report:**
- Includes `response_mode` for post-hoc analysis
- routing_history shows actual execution path
- Degraded mode warnings included in report

### 4.8 Backward Compatibility

When tiered chat components are NOT configured:
- Router can still choose "chat_specialist"
- Orchestrator routes directly to single ChatSpecialist node
- Standard single-perspective response
- No progenitor specialists instantiated
- Zero changes to routing behavior

### 4.9 Configuration in config.yaml

```yaml
# Tiered Chat Subgraph (CORE-CHAT-002)
progenitor_alpha_specialist:
  type: "llm"
  prompt_file: "progenitor_alpha_prompt.md"
  description: "Provides analytical, structured perspective for multi-view responses"

progenitor_bravo_specialist:
  type: "llm"
  prompt_file: "progenitor_bravo_prompt.md"
  description: "Provides contextual, intuitive perspective for multi-view responses"

tiered_synthesizer_specialist:
  type: "procedural"
  description: "Combines Alpha and Bravo perspectives into formatted markdown output"
```

**Key Points:**
- Progenitors are excluded from router's tool schema (internal to subgraph)
- `chat_specialist` node is skipped when tiered components are present
- System auto-detects and enables tiered chat when all three specialists configured

### 4.10 Related Patterns

This Virtual Coordinator pattern is similar to the Hybrid Coordinator pattern used by EndSpecialist:
- EndSpecialist performs inline synthesis (procedural + LLM)
- TieredSynthesizer performs inline combination (procedural only)
- Both write to `final_user_response.md` to signal completion
- Both demonstrate separation between capability declaration and implementation

## 5.0 Pattern: Resilience Layer (Invariants & Monitor)

**Context:** In complex agentic systems, "silent failures" (e.g., infinite loops, malformed state, context corruption) are common and often catastrophic. Relying solely on the LLM to self-correct is insufficient.

**Solution:** The system implements a dedicated **Resilience Layer** that enforces formal system invariants at the code level, acting as a circuit breaker to fail fast and loudly when the system enters an invalid state.

### 5.1 The Invariant Monitor

The `InvariantMonitor` (`app/src/resilience/monitor.py`) is a service that runs *before* every specialist execution. It checks a set of formal rules defined in `app/src/resilience/invariants.py`.

**Key Invariants:**
1.  **Structural Integrity:** Ensures `GraphState` contains all required keys (`messages`, `artifacts`, `scratchpad`, etc.) and correct types.
2.  **Max Turn Count:** Prevents runaway execution by enforcing a hard limit on total turns.
3.  **Loop Detection:** Detects both immediate loops (`A -> A -> A`) and 2-step cycles (`A -> B -> A -> B`) to prevent unproductive infinite loops.

### 5.2 Integration Point

The monitor is integrated directly into the `GraphOrchestrator`'s `create_safe_executor` wrapper. This ensures that **no specialist** can execute if the system is in an invalid state.

```python
# GraphOrchestrator.create_safe_executor
def safe_executor(state: GraphState) -> Dict[str, Any]:
    # ...
    # Fail-fast if the system is in an invalid state
    self.invariant_monitor.check_invariants(state, stage=f"pre-execution:{specialist_name}")
    # ...
```

### 5.3 Observability

The `InvariantMonitor` is instrumented with LangSmith tracing (`@traceable`). In the LangSmith UI, you will see `InvariantMonitor.check_invariants` calls as "tool" runs within the trace, allowing you to verify that checks are passing (or see exactly why they failed).
