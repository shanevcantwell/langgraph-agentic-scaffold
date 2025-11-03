# System Architecture & Developer's Guide
# Version: 3.2
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

## 2.0 System Architecture

The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task.
2.  **Runtime Orchestrator (`RouterSpecialist` & `GraphOrchestrator`):** The `RouterSpecialist` is an agent that makes the turn-by-turn routing decisions *within* the graph. The `GraphOrchestrator` contains the runtime logic (decider functions, safety wrappers) that the graph itself executes.
3.  **Structural Orchestrator (`GraphBuilder`):** A high-level system component responsible for building the `LangGraph` instance and enforcing global rules.

The system also includes a robust set of custom exceptions (e.g., `ProxyError`, `SafetyFilterError`, `RateLimitError`) to provide clear, actionable error messages instead of generic failures, which is critical for debugging agentic workflows.
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
The system uses a framework-native `lifespan` manager in the FastAPI application (`api.py`) to ensure buffered traces are sent before the server process exits. Verify that the `@asynccontextmanager` function named `lifespan` is present in `app/src/api.py`.

## 4.0 Architectural Best Practices & Lessons Learned

### 4.1 Principle: Match Model Capability to Architectural Role

The `router_specialist` is the most critical reasoning component in the architecture. Assigning a small or less capable model to this role is a significant architectural risk and has been observed to cause pathological failures (runaway generation, context collapse).

**Recommendation:** The `router_specialist` should be run by a capable, instruction-tuned model known for reliable tool use (e.g., Gemini Flash, GPT-3.5-Turbo, or larger). Reserve smaller, more efficient models for more constrained, less critical specialist tasks.

### 4.2 Pattern: Intentional vs. Unproductive Loops

The `GraphOrchestrator` includes a generic loop detection mechanism to halt unproductive cycles (e.g., a sequence like `Router -> Specialist A -> Router -> Specialist A ...`). This mechanism inspects the `routing_history` to prevent the system from getting stuck. This is the preferred pattern for creating controlled, stateful cycles.

Intentional loops, such as the "Generate-and-Critique" cycle, are architected differently. They are implemented using conditional edges in the graph that create a direct `Specialist A -> Specialist B -> Specialist A` sub-graph. Because this sub-loop does not repeatedly pass through the main `RouterSpecialist`, it is not flagged by the generic unproductive loop detector. This is the preferred pattern for creating controlled, stateful cycles.

### 4.3 Pattern: Enforce Centralized Control with Coordinated Completion Sequence

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

### 4.4 Contract: The Adapter Robust Parsing Contract

**Principle:** The LLM Adapter layer is solely responsible for abstracting provider-specific idiosyncrasies. This includes inconsistent formatting of structured data responses.

**Policy:** All concrete implementations of `BaseAdapter` MUST adhere to the Robust Parsing Contract. When a specialist requests structured data (e.g., via `output_model_class`), the adapter is responsible for returning a valid, parsed JSON object if one can be reasonably extracted from the provider's raw response.

**Implementation:** To ensure consistency and prevent code duplication, all adapters MUST utilize the `_robustly_parse_json_from_text()` helper method provided by the `BaseAdapter` class as a fallback mechanism. An adapter should only return an empty `json_response` if both a direct parse and the robust fallback parse fail. This contract is non-negotiable and is verified by the system's contract tests (`app/tests/llm/test_adapter_contracts.py`).

### 4.5 Architecture: The 3-Tiered Configuration System

The system's configuration is a three-tiered hierarchy. Understanding this model is essential for both running and extending the system. The layers are resolved at startup by the `ConfigLoader`.

**Tier 1: Secrets (`.env`)**
*   **File:** `.env`
*   **Purpose:** Provides raw secrets and environment-specific connection details (e.g., `GOOGLE_API_KEY`, `LMSTUDIO_BASE_URL`).
*   **Git:** Ignored.

**Tier 2: Architectural Blueprint (`config.yaml`)**  
*   **File:** `config.yaml`
*   **Purpose:** The system's architectural source of truth, managed by the developer. It defines all possible components (specialists) and the workflow structure. It is a pure blueprint of *what* the system can do, but not *how* it does it.
*   **Git:** Committed to source control.

**Tier 3: User Implementation (`user_settings.yaml`)**  
*   **File:** `user_settings.yaml`
*   **Purpose:** Defines the concrete implementation of the system for a given environment. While the file can be absent, a functional system **requires** it to define LLM providers and bind them to specialists. It is the single source of truth for:
    1.  Defining and naming all LLM provider configurations (`llm_providers`). This is where you specify which models to use (e.g., `gemini-2.5-pro`) and what to call them (e.g., `my_strong_model`).
    2.  Binding specialists to those providers (`specialist_model_bindings`).
    3.  Setting a system-wide default model (`default_llm_config`).
*   **Git:** Ignored.

**Example of Merging Logic:**

1.  **Developer defines the architecture in `config.yaml` (no providers here):**
    ```yaml
    # config.yaml
    specialists:
      router_specialist:
        type: "llm"
        # ...
      web_builder:
        type: "llm"
        # ...
    ```

2.  **User defines providers and bindings in `user_settings.yaml`:**
    ```yaml
    # user_settings.yaml
    default_llm_config: "my_fast_model"

    llm_providers:
      my_strong_model:
        type: "gemini"
        api_identifier: "gemini-1.5-pro-latest"
      my_fast_model:
        type: "gemini"
        api_identifier: "gemini-1.5-flash-latest"

    specialist_model_bindings:
      router_specialist: "my_strong_model"
    ```

3.  **Result:** At runtime, the `GraphBuilder` will instantiate the `router_specialist` and, seeing the binding in `user_settings.yaml`, will configure it to use the `my_strong_model` provider. The `web_builder` specialist, having no specific binding, will fall back to using the `my_fast_model` provider as defined by `default_llm_config`.

### 4.6 Container Naming Convention

The `docker-compose.yml` file uses explicit container names (`langgraph-app` and `langgraph-proxy`). This is to prevent conflicts with other projects and to make the containers easily identifiable. It is strongly recommended not to change these names, as it can lead to unexpected behavior and orphaned containers.

## 5.0 How to Extend the System: Creating Specialists

The primary way to extend the system's capabilities is by adding new specialists. The `CREATING_A_NEW_SPECIALIST.md` document provides a comprehensive, step-by-step tutorial for this process.

Please refer to it for:
*   Creating a standard, LLM-based specialist.
*   Creating an advanced, procedural specialist.
*   Best practices for state management and agentic robustness patterns.

## 6.0 Unit Testing Principles

The project has a centralized, fixture-based testing architecture to ensure that unit tests are robust, maintainable, and easy to write. This approach eliminates brittle, ad-hoc mocks and provides a consistent way to test specialists in isolation.
To ensure `pytest` can always find the project's root and the central `conftest.py` file, a `pytest.ini` is placed in the `app/tests/` directory. This file sets `rootdir = ../..`, which is critical for allowing tests to be run directly from within an IDE or from any subdirectory.
 
### 6.1 The Centralized Fixture Architecture (`conftest.py`)

All core architectural components are mocked centrally in `app/tests/conftest.py`. This provides a single source of truth for test dependencies. Key fixtures include `mock_config_loader` and `mock_adapter_factory`.

### 6.2 The `initialized_specialist_factory` (Canonical Fixture)

The cornerstone of the testing strategy is the `initialized_specialist_factory` fixture. This is a factory function that returns a fully initialized specialist instance with all its core dependencies (like the LLM adapter) already mocked.

**This is the canonical way to get a specialist instance for testing.**

**Example Usage:**
```python
# in app/tests/unit/test_my_new_specialist.py

def test_my_logic(initialized_specialist_factory):
    # Get a ready-to-test instance of your specialist
    my_specialist = initialized_specialist_factory("MyNewSpecialist")
    
    # The specialist's LLM adapter is already a mock
    my_specialist.llm_adapter.invoke.return_value = {"text_response": "mocked LLM output"}
    
    # ... proceed with your test logic ...
```

### 6.3 Mandatory Policy for New Tests

1.  **MUST use the `initialized_specialist_factory`:** All new unit tests for specialists **must** use this fixture to obtain the specialist instance under test.
2.  **MUST NOT implement local mocks:** New tests **must not** create their own local mocks for core components like `ConfigLoader`, `AdapterFactory`, or the LLM adapter. Rely on the centralized fixtures to provide these.

Adhering to these principles is mandatory to prevent architectural drift and ensure the long-term stability and maintainability of the test suite.
