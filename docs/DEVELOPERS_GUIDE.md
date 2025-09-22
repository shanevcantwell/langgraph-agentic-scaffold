# System Architecture & Developer's Guide
# Version: 3.2
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

## 2.0 System Architecture

The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task.
2.  **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph.
3.  **Structural Orchestrator (`ChiefOfStaff`):** A high-level system component responsible for building the `LangGraph` instance and enforcing global rules.

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

### 4.1.1 Intentional vs. Unproductive Loops

The `ChiefOfStaff` includes a generic loop detection mechanism to halt unproductive cycles (e.g., a sequence like `Router -> Specialist A -> Router -> Specialist A ...`). This mechanism inspects the `routing_history` to prevent the system from getting stuck.

Intentional loops, such as the "Generate-and-Critique" cycle, are architected differently. They are implemented using conditional edges in the graph that create a direct `Specialist A -> Specialist B -> Specialist A` sub-graph. Because this sub-loop does not repeatedly pass through the main `RouterSpecialist`, it is not flagged by the generic unproductive loop detector. This is the preferred pattern for creating controlled, stateful cycles.

### 4.2 Implement Robust Loop Control

Off-by-one errors in agentic loops can be common. Ensure that loop termination logic in stateful specialists uses strict inequality (`<`) rather than (`<=`) to compare the current iteration count against the maximum number of cycles.

### 4.3 Enforce Centralized Control with Three-Stage Termination

To ensure system stability and predictable behavior, this architecture employs a mandatory **termination sequence**. Functional specialists are forbidden from terminating the graph directly. Instead, they signal task completion, which triggers a standardized, sequential shutdown process managed by the graph's structure itself.

This pattern is critical for ensuring that final housekeeping tasks, such as synthesizing a user-friendly response and generating an archive report, are always executed. The termination of the workflow is a deliberate, centralized, and observable event enshrined in the graph's structure.

The process is as follows:

1.  **Stage 1: Signal Completion**
    *   A functional specialist (e.g., `web_builder`) completes its primary task.
    *   It signals this completion by including `task_is_complete: True` in its return state.
    *   Optionally, it contributes a human-readable summary of its action to the `user_response_snippets` list within the `scratchpad`.
    *   The `ChiefOfStaff` configures a conditional edge in the graph that checks for the `task_is_complete` flag. When this flag is `True`, graph execution is routed to the `response_synthesizer_specialist` instead of back to the main `router_specialist`.

2.  **Stage 2: Synthesize & Archive**
    *   The `response_synthesizer_specialist` runs, taking the snippets from `scratchpad['user_response_snippets']` and generating a `final_user_response.md` artifact.
    *   The `ChiefOfStaff` wires a direct, non-conditional edge from the `response_synthesizer_specialist` to the `archiver_specialist`.
    *   The `archiver_specialist` runs, consuming the state (including the new `final_user_response.md`) and generating the final `archive_report.md`.

3.  **Stage 3: Terminate**
    *   The `ChiefOfStaff` wires the `archiver_specialist` directly to the special `END` node.
    *   After the `archiver_specialist` completes its run, the graph execution halts cleanly.

This explicit `... -> (task_is_complete?) -> Response Synthesizer -> Archiver -> END` sequence is defined in the `ChiefOfStaff` when the graph is compiled. This structural guarantee ensures that termination is always handled in a consistent, predictable manner, which significantly enhances the system's robustness.

### 4.4 The Adapter Robust Parsing Contract

**Principle:** The LLM Adapter layer is solely responsible for abstracting provider-specific idiosyncrasies. This includes inconsistent formatting of structured data responses.

**Policy:** All concrete implementations of `BaseAdapter` MUST adhere to the Robust Parsing Contract. When a specialist requests structured data (e.g., via `output_model_class`), the adapter is responsible for returning a valid, parsed JSON object if one can be reasonably extracted from the provider's raw response.

**Implementation:** To ensure consistency and prevent code duplication, all adapters MUST utilize the `_robustly_parse_json_from_text()` helper method provided by the `BaseAdapter` class as a fallback mechanism. An adapter should only return an empty `json_response` if both a direct parse and the robust fallback parse fail. This contract is non-negotiable and is verified by the system's contract tests (`app/tests/llm/test_adapter_contracts.py`).

### 4.5 Understanding the 3-Tiered Configuration System

The system's configuration is not a single file but a three-tiered hierarchy. Understanding this model is essential for both running and extending the system. The layers are resolved from bottom to top:

**Tier 1: Secrets (`.env`)**
This file provides the raw secrets and connection details (API keys, URLs). It is never committed to source control.

**Tier 2: Architectural Blueprint (`config.yaml`)**  
This is the system's architectural source of truth, managed by the developer. It defines all possible components (specialists, LLM provider configurations) that can be used in the system.

**Tier 3: User Overrides (`user_settings.yaml`)**  
This optional file allows an end-user to customize the system's behavior without modifying the core architecture. It is used to bind specific specialists to the LLM provider configurations defined in `config.yaml`.

At startup, the `ConfigLoader` merges these layers. It starts with the blueprint (Tier 2) and then applies any overrides from your user settings (Tier 3). The application components then use this final configuration to function, pulling in the necessary secrets from the environment (Tier 1) as needed.

**Example of Merging Logic:**

1.  **Developer defines the architecture in `config.yaml`:**
    ```yaml
    # config.yaml
    llm_providers:
      powerful_model:
        type: "gemini"
        api_identifier: "gemini-1.5-pro"
      fast_model:
        type: "gemini"
        api_identifier: "gemini-1.5-flash"
    
    specialists:
      router_specialist:
        type: "llm"
        # ...
    ```

2.  **User chooses a model in `user_settings.yaml`:**
    ```yaml
    # user_settings.yaml
    specialist_model_bindings:
      router_specialist: "fast_model" # User wants speed over power for routing.
    ```

3.  **Result:** At runtime, the `ChiefOfStaff` will instantiate the `router_specialist` and configure it to use the `fast_model` provider configuration (`gemini-1.5-flash`).

## 5.0 How to Extend the System: Creating Specialists

The primary way to extend the system's capabilities is by adding new specialists. The `CREATING_A_NEW_SPECIALIST.md` document provides a comprehensive, step-by-step tutorial for this process.

Please refer to it for:
*   Creating a standard, LLM-based specialist.
*   Creating an advanced, procedural specialist.
*   Best practices for state management and agentic robustness patterns.

```markdown
# docs/CREATING_A_NEW_SPECIALIST.md

### 5.4 Advanced: Creating a Procedural Specialist

A "procedural" specialist is one that executes deterministic code, rather than making a conversational request to an LLM. This pattern is ideal for deterministic tasks or for safely integrating external tools using the "Plan and Execute" pattern. For a detailed example of integrating a tool like `open-interpreter`, please refer to the source code of the `OpenInterpreterSpecialist`.
See the tutorial in `CREATING_A_NEW_SPECIALIST.md` for a complete implementation guide.

### 4.5 Understanding the 3-Tiered Configuration System

The system's configuration is not a single file but a three-tiered hierarchy. Understanding this model is essential for both running and extending the system. The layers are resolved from bottom to top:

**Tier 1: Secrets (`.env`)**
This file provides the raw secrets and connection details (API keys, URLs). It is never committed to source control.

**Tier 2: Architectural Blueprint (`config.yaml`)**
This is the system's source of truth. It defines all possible components (specialists, providers) and sets the *default* working configuration. For example, it might default the `CriticSpecialist` to use the `gemini_pro` provider.

**Tier 3: User Overrides (`user_settings.yaml`)**
This optional file allows you to override the defaults from `config.yaml` without editing the core architecture. For example, by adding `critic_specialist: "lmstudio_specialist"` to this file, you instruct the system to ignore the Tier 2 default and use your local model instead.

At startup, the `ConfigLoader` merges these layers. It starts with the blueprint (Tier 2) and then applies any overrides from your user settings (Tier 3). The application components then use this final configuration to function, pulling in the necessary secrets from the environment (Tier 1) as needed.
...
```
