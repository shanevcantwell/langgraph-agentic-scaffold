# How the Graph is Built: A Deep Dive into GraphBuilder and GraphOrchestrator

This document provides a definitive, step-by-step explanation of how the `GraphBuilder` class constructs the `LangGraph` instance, using the `GraphOrchestrator` to manage runtime logic. The architecture is designed to be robust and declarative, and this guide serves as the canonical reference for the implementation.

## Core Philosophy: Separating Build-Time and Run-Time

The system's architecture is designed around a clean separation of concerns between the "build-time" construction of the graph and its "run-time" execution.

*   **`GraphBuilder`:** This component is responsible for the one-time task of reading configuration, instantiating all specialists, and compiling the final, executable `StateGraph`. It is the **structural orchestrator**.
*   **`GraphOrchestrator`:** This component contains all the logic that is executed *by* the graph at runtime, such as the decider functions for conditional edges. It is the **runtime orchestrator**.

The construction process follows a clear, sequential order within the `GraphBuilder`'s `__init__` and `build` methods.

---

## Step 1: Loading and Configuring Specialists (`_load_and_configure_specialists` in GraphBuilder)

This is the foundational step where the system discovers and prepares all available "workers."

1.  **Read Configuration:** The process begins by loading the merged configuration from `config.yaml` and `user_settings.yaml`.

2.  **Dynamic Instantiation:** The `GraphBuilder` iterates through each specialist defined in the `specialists` section of the configuration.
    *   It uses the `get_specialist_class` helper to dynamically import the specialist's Python class based on its name (e.g., `"file_specialist"` maps to `FileSpecialist`).
    *   Each specialist is instantiated, injecting its specific configuration block and name. This decouples specialists from global configuration.

3.  **Specialized Instantiation (Handling Edge Cases):**
    *   **`CriticSpecialist`:** This specialist has a complex dependency. The `GraphBuilder` reads the `critique_strategy` sub-configuration, instantiates the required strategy (e.g., `LLMCritiqueStrategy`), creates a dedicated LLM adapter for it, and injects the strategy instance into the `CriticSpecialist`'s constructor.
    *   **`EndSpecialist`:** This procedural coordinator needs the configurations for the specialists it manages (`ResponseSynthesizer` and `Archiver`). The `GraphBuilder` gathers these configurations and passes them, along with the `AdapterFactory`, to the `EndSpecialist`'s constructor.

4.  **LLM Adapter Injection:** For any specialist that requires an LLM (indicated by the `llm_config` key), the `GraphBuilder` invokes the `AdapterFactory` to create and attach the appropriate `BaseAdapter` instance.
    *   **Dynamic Prompts:** For orchestration specialists like `RouterSpecialist` and `PromptTriageSpecialist`, adapter creation is deferred. Their system prompts are dynamically constructed with a real-time list of available specialists to ensure they always have the most current information.

5.  **Pre-Flight Checks & Disabling:** After instantiation, each specialist's `_perform_pre_flight_checks()` method is called. If a specialist fails its checks (e.g., a required dependency is missing) or is explicitly disabled in its config, it is logged and excluded from the final list of "loaded" specialists. This makes the system resilient to partial failures.

---

## Step 2: Building the Graph (`build` in GraphBuilder)

Once all specialists are loaded and configured, the `build` method assembles the `StateGraph`.

### 2.1. Adding Nodes (`_add_nodes_to_graph`)

*   Each successfully loaded specialist is added as a node to the graph.
*   Crucially, every specialist's `execute` method (except for the `RouterSpecialist`) is wrapped in the `GraphOrchestrator.create_safe_executor` decorator. This wrapper is a non-negotiable gatekeeper that:
    1.  **Enforces Preconditions:** Checks for `requires_artifacts` at runtime before executing the specialist.
    2.  **Handles Exceptions:** Catches any unhandled exceptions from a specialist, generates a detailed `error_report.md`, and prevents the entire graph from crashing.
    3.  **Prevents State Corruption:** Sanitizes the specialist's output to prevent forbidden modifications (e.g., changing `turn_count`).

### 2.2. Wiring Edges (`_wire_hub_and_spoke_edges`)

This is where the agent's behavior and control flow are defined. The system uses a hybrid approach of conditional and direct edges, all managed by the `GraphOrchestrator`.

#### The Main Loop (Hub-and-Spoke)

1.  **Router to Specialists:** A conditional edge is added from the `router_specialist`. The `GraphOrchestrator.route_to_next_specialist` function reads the `next_specialist` key from the state and directs the graph to the chosen specialist node.

2.  **Specialists to Decider:** For all *standard* functional specialists, an edge is added that points to the `GraphOrchestrator.check_task_completion` decider function. This function is the primary mechanism for termination:
    *   If `task_is_complete` is `True` in the state, it routes to the `end_specialist`.
    *   Otherwise, it routes back to the `router_specialist`, completing the "hub-and-spoke" loop.

#### The "Express Lanes" (Specialized Conditional Routing)

The system uses explicit, high-priority conditional edges for specific, well-defined sub-workflows, bypassing the main router for efficiency.

*   **The "Generate-and-Critique" Loop (ADR-CORE-012):**

    Creates a **bidirectional subgraph** for iterative refinement:

    ```
    Router → web_builder → critic_specialist
                ↑              ↓
                └── REVISE ────┘
                    ACCEPT → check_task_completion → END
    ```

    **Key Components:**
    1. **Direct Edge:** `web_builder → critic_specialist` (bypasses router)
    2. **Exclusion:** `web_builder` excluded from hub-and-spoke routing
    3. **Conditional Edge:** `critic_specialist → after_critique_decider`
    4. **Config:** `critic_specialist.revision_target: "web_builder"`

    **Flow:**
    - Router routes to `web_builder` (generates initial UI)
    - `web_builder` completes → **directly** to `critic_specialist` (no router hop)
    - `critic_specialist` reviews artifact → `after_critique_decider`
    - **REVISE** → routes back to `web_builder` (refine based on feedback)
    - **ACCEPT** → routes to `check_task_completion` (begin termination)

    **Critical Configuration:**
    ```yaml
    critic_specialist:
      revision_target: "web_builder"  # MUST match generator specialist
    ```

    **Why This Pattern:**
    - ✅ **Efficiency:** 66% fewer hops (1 edge vs 3 per iteration)
    - ✅ **Prevents False Loop Detection:** Valid refinement cycles don't trigger loop detection
    - ✅ **Architectural Clarity:** Intent is explicit in code and config
    - ⚠️ **Regression Risk:** Lost across LLM context windows - well documented now

*   **The Termination Sequence:**
    *   The `end_specialist` is the designated finalizer. A direct, non-conditional edge is wired from the `end_specialist` node to the special `END` node of the graph. This guarantees that once the finalizer runs, the workflow terminates cleanly.

#### Parallel Execution with Fan-Out/Fan-In (CORE-CHAT-002)

The system supports parallel execution patterns using LangGraph's fan-out and fan-in primitives. This is exemplified by the **Tiered Chat Subgraph**.

**Fan-Out (Parallel Dispatch):**

The `GraphOrchestrator.route_to_next_specialist()` conditional edge function can return a **list** of specialist names to trigger parallel execution:

```python
def route_to_next_specialist(self, state: GraphState) -> str | list[str]:
    next_specialist = state.get("next_specialist")

    # Fan-out: Return list for parallel execution
    if next_specialist == "chat_specialist":
        if self._has_tiered_chat_specialists():
            return ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]

    # Normal routing: Return single specialist name
    return next_specialist
```

When a list is returned, LangGraph executes all listed specialists **in parallel** (concurrently), not sequentially.

**Fan-In (Join Point):**

To wait for multiple parallel predecessors before executing a join node, use the **array syntax** for edges:

```python
# CRITICAL: Array syntax creates proper join behavior
workflow.add_edge(
    ["progenitor_alpha_specialist", "progenitor_bravo_specialist"],
    "tiered_synthesizer_specialist"
)
```

**Key Points:**
- The array `["node_a", "node_b"]` tells LangGraph: "Wait for BOTH nodes to complete before executing the target"
- Without array syntax, adding separate edges would cause the target to execute twice (once per predecessor)
- The join node receives the **merged state** from both parallel branches (state reducers handle merging)

**State Merging with Reducers:**

LangGraph's state reducers define how parallel branches merge their state updates:

```python
# In GraphState definition
class GraphState(TypedDict):
    messages: Annotated[list, operator.add]           # Concatenate lists
    artifacts: Annotated[dict, operator.ior]          # Merge dicts (|= operator)
    routing_history: Annotated[list, operator.add]    # Concatenate lists
```

When both progenitors complete:
- Their `messages` lists are concatenated
- Their `artifacts` dicts are merged (latter wins on key conflicts)
- Their `routing_history` entries are concatenated

**Conditional Edge After Join:**

After the join node completes, route it using standard conditional edges:

```python
workflow.add_conditional_edges(
    "tiered_synthesizer_specialist",
    self.orchestrator.check_task_completion,
    {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name}
)
```

**Virtual Coordinator Pattern:**

The tiered chat implementation uses a "virtual coordinator" pattern:
- Router chooses `"chat_specialist"` (capability declaration)
- Orchestrator intercepts and dispatches to progenitors (implementation detail)
- `chat_specialist` node is **skipped** in graph construction when tiered components present
- Progenitors are **excluded from router's tool schema** (internal to subgraph)

**Graph Construction Logic:**

```python
def _add_nodes_to_graph(self, workflow: StateGraph):
    has_tiered_chat = self._has_tiered_chat_specialists()

    for name, instance in self.specialists.items():
        # Skip chat_specialist node when tiered chat enabled
        if has_tiered_chat and name == "chat_specialist":
            logger.info(f"Skipping {name} node - tiered chat subgraph enabled")
            continue

        # Add specialist as node with safe executor wrapper
        safe_executor = self.orchestrator.create_safe_executor(instance)
        workflow.add_node(name, safe_executor)

def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
    has_tiered_chat = self._has_tiered_chat_specialists()

    if has_tiered_chat:
        # Wire fan-in edge (join point)
        workflow.add_edge(
            ["progenitor_alpha_specialist", "progenitor_bravo_specialist"],
            "tiered_synthesizer_specialist"
        )

        # Wire synthesizer to standard task completion check
        workflow.add_conditional_edges(
            "tiered_synthesizer_specialist",
            self.orchestrator.check_task_completion,
            {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name}
        )
```

**Observability:**

LangSmith traces show parallel execution visually:
- Both progenitors appear at the same "level" in the trace timeline
- Wall-clock time for parallel section ≈ max(alpha_time, bravo_time), not alpha_time + bravo_time
- `routing_history` shows execution order: `["router_specialist", "progenitor_alpha_specialist", "progenitor_bravo_specialist", "tiered_synthesizer_specialist"]`

**Reference:** See section 4.7 in DEVELOPERS_GUIDE.md for detailed architectural patterns and ADR CORE-CHAT-002 for implementation rationale.

### 2.3. Setting the Entry Point and Compiling

1.  **Entry Point:** The graph's entry point is set to the value from `workflow.entry_point` in `config.yaml` (which defaults to `router_specialist`).

2.  **Compilation:** Finally, `workflow.compile()` is called. This returns the immutable, compiled `LangGraph` application, ready to process requests.

---

## Visual Summary

```mermaid
graph TD
    subgraph "GraphBuilder: Initialization"
        A[Load config.yaml] --> B{Instantiate Specialists};
        B --> C{Inject LLM Adapters};
        C --> D[Run Pre-Flight Checks];
    end

    subgraph "GraphBuilder: Graph Construction"
        E[Create StateGraph] --> F[Add Nodes w/ SafeExecutor from GraphOrchestrator];
        F --> G{Wire Edges using GraphOrchestrator deciders};
        G -- Hub-and-Spoke --> G1(Router --> Specialists);
        G -- Hub-and-Spoke --> G2(Specialists --> check_task_completion);
        G -- Express Lane --> G3(Critic --> after_critique_decider);
        G -- Termination --> G4(EndSpecialist --> END);
        G --> H[Set Entry Point];
        H --> I[Compile Graph];
    end

    Initialization --> "GraphBuilder: Graph Construction"
```