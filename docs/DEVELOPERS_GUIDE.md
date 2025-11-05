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

### 4.7 Pattern: Virtual Coordinator with Parallel Execution (CORE-CHAT-002)

The Virtual Coordinator pattern enables the system to transparently upgrade single-node capabilities into multi-node subgraphs without exposing implementation details to the router. This pattern is exemplified by the **Tiered Chat Subgraph**, which transforms a single chat specialist into a parallel multi-perspective system.

#### 4.7.1 Architectural Overview

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

#### 4.7.2 Implementation Details

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

#### 4.7.3 Graceful Degradation Strategy (CORE-CHAT-002.1)

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

#### 4.7.4 Efficiency Optimization: Skip Redundant Synthesis

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

#### 4.7.5 Model Binding Configuration

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

#### 4.7.6 Observability

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

#### 4.7.7 Backward Compatibility

When tiered chat components are NOT configured:
- Router can still choose "chat_specialist"
- Orchestrator routes directly to single ChatSpecialist node
- Standard single-perspective response
- No progenitor specialists instantiated
- Zero changes to routing behavior

#### 4.7.8 Configuration in config.yaml

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

#### 4.7.9 Related Patterns

This Virtual Coordinator pattern is similar to the Hybrid Coordinator pattern used by EndSpecialist:
- EndSpecialist performs inline synthesis (procedural + LLM)
- TieredSynthesizer performs inline combination (procedural only)
- Both write to `final_user_response.md` to signal completion
- Both demonstrate separation between capability declaration and implementation

**References:**
- ADR CORE-CHAT-002: Tiered Chat Subgraph (Fan-Out)
- ADR CORE-CHAT-002.1: Graceful Degradation Strategy
- ADR CORE-CHAT-002.2: Virtual Coordinator Pattern
- ADR CORE-CHAT-002_FINAL_DECISIONS: Consolidated implementation decisions

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
