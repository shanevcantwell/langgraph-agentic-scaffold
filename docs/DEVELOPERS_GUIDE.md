# System Architecture & Developer's Guide
# Version: 3.1
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

## 2.0 System Architecture

The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task.
2.  **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph.
3.  **Structural Orchestrator (`ChiefOfStaff`):** A high-level system component responsible for building the `LangGraph` instance and enforcing global rules.

### 2.1 Proposed Architectural Evolution: Generic State Management
**Status: Implemented.** The architecture has adopted a robust state management model. Specialist-specific state fields (e.g., `html_artifact`) have been deprecated in favor of two generic dictionaries in the `GraphState`:
*   `artifacts`: A "heap" for significant data outputs.
*   `scratchpad`: A "register" for specialists' private, transient state (e.g., loop counters).

All new specialists **must** be designed using this pattern to ensure forward compatibility and system stability.

## 3.0 Observability with LangSmith (Essential for Development)

For any non-trivial workflow, observability is not optional. The complexity of multi-agent systems makes debugging with logs alone extremely difficult. This scaffold is architected for seamless integration with LangSmith.

### 3.1 Why LangSmith is Critical

*   **Visual Tracing:** See a complete, hierarchical trace of every run, showing which specialists ran, in what order, and with what inputs/outputs.
*   **State Inspection:** Click on any step in the trace to inspect the full `GraphState` at that point in time.
*   **Error Isolation:** Failed steps are highlighted in red, instantly showing the point of failure and the state that caused it.
*   **Performance Analysis:** Easily track token counts, latency, and costs for each LLM call.

### 3.2 Enabling LangSmith

Integration is a simple, two-step configuration process.

**Step 1: Configure Environment Variables**
Add the correct V2 tracing variables to your `.env` file. Ensure the `LANGCHAIN_PROJECT` name exactly matches the project name in your LangSmith UI.

```dotenv
# .env file

# --- LangSmith V2 Configuration (Authoritative) ---
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
export LANGCHAIN_API_KEY="ls__your_api_key_goes_here"
export LANGCHAIN_PROJECT="your-exact-project-name-from-the-ui"
```

**Step 2: Ensure Graceful Shutdown**
The system uses a framework-native lifecycle hook in the FastAPI application to ensure buffered traces are sent before the server process exits. Verify that the `@app.on_event("shutdown")` handler is present in `app/src/api.py`.

## 4.0 Architectural Best Practices & Lessons Learned

### 4.1 Match Component Capability to Architectural Role

The `router_specialist` is the most critical reasoning component in the architecture. Assigning a small or less capable model to this role is a significant architectural risk and has been observed to cause pathological failures (runaway generation, context collapse).

**Recommendation:** The `router_specialist` should be run by a capable, instruction-tuned model known for reliable tool use (e.g., Gemini Flash, GPT-3.5-Turbo, or larger). Reserve smaller, more efficient models for more constrained, less critical specialist tasks.

### 4.2 Implement Robust Loop Control

Off-by-one errors in agentic loops can be common. Ensure that loop termination logic in stateful specialists uses strict inequality (`<`) rather than (`<=`) to compare the current iteration count against the maximum number of cycles.

### 4.3 Enforce Centralized Control with Two-Stage Termination

To ensure system stability and prevent non-deterministic behavior, this architecture employs a mandatory **Three-Stage Termination Pattern**. Functional specialists are forbidden from terminating the graph directly. Only the `router_specialist` holds the authority to route to the `__end__` state.

This pattern is critical for ensuring that final housekeeping tasks, such as synthesizing a user-friendly response and generating an archive report, are always executed. The termination of the workflow is a deliberate, centralized, and observable event enshrined in the graph's structure.

The process is as follows:

1.  **Stage 1: Signal Completion & Route to Synthesizer**
    *   A functional specialist (e.g., `web_builder`) completes its primary task.
    *   It signals this completion by including `task_is_complete: True` in its return state.
    *   Optionally, it contributes a human-readable summary of its action to the `user_response_snippets` list within the `scratchpad`.
    *   The `router_specialist` observes the `task_is_complete` flag and routes control to the `response_synthesizer_specialist`.

2.  **Stage 2: Synthesize, Archive, and Verify**
    *   The `response_synthesizer_specialist` runs, taking the snippets from `scratchpad['user_response_snippets']` and generating a `final_user_response.md` artifact.
    *   The graph's structure then explicitly routes control from the synthesizer to the `archiver_specialist`.
    *   The `archiver_specialist` runs, consuming the `final_user_response.md` artifact and generating the final `archive_report.md` artifact.
    *   Crucially, the `archiver_specialist` does **not** end the graph. It returns control back to the `router_specialist`.

3.  **Stage 3: Final Review and Termination**
    *   The `router_specialist` now observes the presence of the `artifacts['archive_report.md']` in the state. This is the definitive signal that the workflow is complete.
    *   The router then makes the final, authoritative decision to route to `__end__`, formally terminating the graph.

This explicit `... -> Router -> Synthesizer -> Archiver -> Router -> END` sequence is defined in the `ChiefOfStaff` and guarantees that the `router_specialist` is the sole component responsible for managing the graph's lifecycle, which significantly enhances the system's predictability and robustness.

### 4.4 The Adapter Robust Parsing Contract

**Principle:** The LLM Adapter layer is solely responsible for abstracting provider-specific idiosyncrasies. This includes inconsistent formatting of structured data responses.

**Policy:** All concrete implementations of `BaseAdapter` MUST adhere to the Robust Parsing Contract. When a specialist requests structured data (e.g., via `output_model_class`), the adapter is responsible for returning a valid, parsed JSON object if one can be reasonably extracted from the provider's raw response.

**Implementation:** To ensure consistency and prevent code duplication, all adapters MUST utilize the `_robustly_parse_json_from_text()` helper method provided by the `BaseAdapter` class as a fallback mechanism. An adapter should only return an empty `json_response` if both a direct parse and the robust fallback parse fail. This contract is non-negotiable and is verified by the system's contract tests (`app/tests/llm/test_adapter_contracts.py`).

## 5.0 How to Extend the System: Creating Specialists

The primary way to extend the system's capabilities is by adding new specialists. This section provides a detailed, step-by-step walkthrough.
For a detailed, step-by-step tutorial on creating a new specialist, please see `CREATING_A_NEW_SPECIALIST.md`.

### 5.3 Specialist Best Practices

For guidance on best practices, including state management and agentic robustness patterns, please refer to the `CREATING_A_NEW_SPECIALIST.md` document.

### 5.4 Advanced: Creating a Procedural Specialist

A "procedural" specialist is one that executes deterministic code, rather than making a conversational request to an LLM. This pattern is ideal for deterministic tasks or for safely integrating external tools using the "Plan and Execute" pattern. For a detailed example of integrating a tool like `open-interpreter`, please refer to the source code of the `OpenInterpreterSpecialist`.
See the tutorial in `CREATING_A_NEW_SPECIALIST.md` for a complete implementation guide.
