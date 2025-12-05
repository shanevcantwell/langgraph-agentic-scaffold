# System Architecture

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

## 2.0 System Architecture

The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task.
2. **Runtime Orchestrator (`RouterSpecialist` & `GraphOrchestrator`):** The `RouterSpecialist` is an agent that makes the turn-by-turn routing decisions *within* the graph. The `GraphOrchestrator` contains the runtime logic (decider functions) that the graph itself executes.
3.  **Structural Orchestrator (`GraphBuilder`):** A high-level system component responsible for building the `LangGraph` instance and enforcing global rules.
4.  **Execution Safety (`NodeExecutor`):** A dedicated component that wraps specialist execution to enforce invariants, handle errors, and manage circuit breakers.

The system also includes a robust set of custom exceptions (e.g., `ProxyError`, `SafetyFilterError`, `RateLimitError`) to provide clear, actionable error messages instead of generic failures, which is critical for debugging agentic workflows.

## 2.1 State Management Architecture

The system maintains three distinct state layers with strict separation of concerns:

### Root GraphState (Orchestration Only)
Core system fields managed by the graph infrastructure:
- `messages`: Permanent conversation history (LangChain Message objects)
- `routing_history`: Execution path tracking
- `turn_count`: Recursion control
- `artifacts`: Structured outputs for cross-specialist communication

### Scratchpad (Transient Signals)
Ephemeral specialist-to-specialist communication cleared after routing:
- `recommended_specialists`: Routing suggestions from triage/error handlers
- `error_report`: Failure signals for orchestrator handling
- `context_plan`: Context-gathering instructions from triage
- `user_response_snippets`: Response fragments for synthesis

### Artifacts (Structured Outputs)
Persistent structured data for consumption by other specialists:
- Named keys for specialist outputs (e.g., `alpha_response`, `bravo_response`)
- `final_user_response.md`: Synthesized final response
- `archive_report.md`: Workflow completion report

**Implementation Pattern:**

```python
def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
    # Read from scratchpad
    scratchpad = state.get("scratchpad", {})
    recommendations = scratchpad.get("recommended_specialists")

    # Write to scratchpad (transient) and artifacts (persistent)
    return {
        "scratchpad": {
            "recommended_specialists": ["file_specialist"],
            "error_report": "Needs file context"
        },
        "artifacts": {
            "analysis_result": {"findings": [...]}
        }
    }
```

**Architectural Rationale (ADR-CORE-004):**
- Root state contains only orchestration primitives
- Scratchpad enforces signal ephemerality (prevents state bloat)
- Artifacts provide structured cross-specialist contracts
- Clear boundaries prevent specialist-specific fields from polluting root state

## 2.2 The Heap (Manifest Manager)

"The Heap" is the system's structured context management layer, implemented via the `ManifestManager`. It solves the problem of context fragmentation by providing a unified interface for merging, deduplicating, and retrieving context from multiple sources.

*   **Purpose:** To maintain a coherent view of the "world state" across multiple specialist turns.
*   **Mechanism:**
    *   **Merging:** Intelligently combines new context with existing context, resolving conflicts.
    *   **Deduplication:** Prevents redundant information from cluttering the context window.
    *   **Manifest:** A structured record of all active context items.

The `ManifestManager` is used by specialists (e.g., `DialogueSpecialist`) to process incoming information before it is presented to the LLM or stored in artifacts.

## 2.3 Convening of the Tribes (Orchestration)

The "Convening of the Tribes" (ADR-CORE-023) is the system's advanced orchestration layer, designed to manage multi-model collaboration and persistent state.

*   **TribeConductor (The CPU):** The central node that manages the execution cycle. It handles context switching (loading/saving branches), coordinates synchronous debates (Fishbowl), and triggers synthesis events.
*   **AgentRouter (The Dispatcher):** Maps abstract `AgentAffinity` (e.g., `ARCHITECTURE`, `IMPLEMENTATION`) to concrete specialist IDs. This allows the system to be model-agnostic.
*   **SemanticFirewall (The Filter):** A security and hygiene layer that sits between the Heap (Disk) and the Stack (Context Window). It sanitizes inputs to prevent injection attacks and sanitizes outputs to prevent "slop" from polluting the permanent record.

## 2.4 Deep Research (Focused Investigation)

The "Deep Research" pipeline (ADR-CORE-024) provides a focused investigation capability that separates execution from judgment.

*   **ResearchOrchestrator:** The controller that manages the Search → Browse → Judge → Synthesize loop.
*   **Primitives ("Dumb Tools"):** `WebSpecialist` (Search) and `BrowseSpecialist` (Fetch) are pure execution workers with no internal LLM loop.
*   **InferenceService (Judgment):** An MCP service that provides pure semantic judgment (Relevance, Contradiction, Quality) without side effects.
*   **Synthesizer:** An agent that consumes research findings to generate comprehensive reports.

## 2.5 Triage Recommendations Flow

The system implements an **advisory routing guidance pattern** where the `TriageArchitect` specialist analyzes the user's request and recommends appropriate specialists to handle the task after context gathering completes.

### Architecture Overview

**Flow Diagram:**
```
User Request
    ↓
TriageArchitect (analyzes request, creates ContextPlan)
    ├─ actions: [RESEARCH, READ_FILE, etc.]
    └─ recommended_specialists: ["project_director", "chat_specialist"]  ← Advisory guidance
    ↓
FacilitatorSpecialist (executes actions, gathers context)
    ↓
RouterSpecialist (receives recommendations, makes final decision)
    ├─ Filters recommendations against available menu
    ├─ Distinguishes advisory vs. dependency requirements
    └─ Routes to appropriate specialist
```

### Key Components

**1. ContextPlan Schema** (`app/src/interface/context_schema.py`):
```python
class ContextPlan(BaseModel):
    actions: List[ContextAction] = Field(default_factory=list)
    reasoning: str = Field(..., description="Why these actions are needed")
    recommended_specialists: List[str] = Field(
        default_factory=list,
        description="Specialists recommended to handle the user's request"
    )
```

## 2.3 Resilience Patterns (Escape Hatches)

To prevent "Hallucination Loops" where agents guess filenames or invent data, the system implements a set of **Escape Hatch Protocols** across all specialists.

### The "Polyglot Constraint" Strategy
Each specialist has a specific "Anti-Hallucination Dialect" tailored to its failure mode:

1.  **Epistemological Constraint (Researcher):** "Only cite facts explicitly present in search snippets. Do not use internal training data."
2.  **Ontological Constraint (Data Extractor):** "If data is missing, return `null`. Do not invent values to fill the schema."
3.  **Operational Constraint (File Ops):** "Atomic Planning Rule: You cannot READ a file you have not LISTED. Ignore context errors if a valid list exists."
4.  **Scope Constraint (Web Builder):** "If requirements are vague, build a Wireframe/Prototype. Do not guess the design."

### The Strategy Pattern for Tool Execution
To support modular tool implementations (e.g., switching search providers), the system uses a **Strategy Pattern** in the `ContextAction` schema.

```python
class ContextAction(BaseModel):
    type: ContextActionType
    target: str
    strategy: Optional[str] = None  # e.g., "google", "fast", "deep_dive"
```

This allows the **Triage Architect** (Governance) to specify *how* a task should be performed, while the **Specialist** (Capability) selects the appropriate concrete implementation (Strategy) at runtime.

**2. TriageArchitect** (`app/src/specialists/triage_architect.py`):
- Analyzes user request and creates structured ContextPlan
- Recommends 1-3 specialists based on task type
- Populates `scratchpad.recommended_specialists` for router consumption

**3. RouterSpecialist Recommendation Handling** (`app/src/specialists/router_specialist.py`):
- Receives recommendations from `scratchpad.recommended_specialists`
- Filters recommendations against currently available specialists
- Excludes planning specialists (triage/facilitator) after context gathering
- Distinguishes between:
  - **Advisory recommendations** (from triage): Guidance, not mandatory
  - **Dependency requirements** (from failed specialists): Hard requirements

### Advisory vs. Dependency Distinction

**Advisory Recommendations (Triage):**
```
Router Prompt:
"TRIAGE SUGGESTIONS (ADVISORY, NOT MANDATORY):
The triage specialist recommends considering: researcher_specialist, chat_specialist
These are suggestions based on initial analysis. You may choose a different specialist if you have stronger reasoning."
```

**Dependency Requirements (Specialist Error):**
```
Router Prompt:
"Dependency Requirement:
The 'text_analysis_specialist' cannot proceed without artifacts from 'file_specialist'.
Please route to 'file_specialist' to satisfy this dependency."
```

The distinction is determined by checking `routing_history`:
- If last non-planning specialist made the recommendation → Dependency (mandatory)
- Otherwise → Advisory (guidance only)

### Context-Aware Routing

After context gathering completes (`gathered_context` artifact exists):
1. Planning specialists (`triage_architect`, `facilitator_specialist`) excluded from routing menu
2. Recommendations filtered to only include available specialists
3. "CONTEXT GATHERING COMPLETE" note added to router prompt
4. Router chooses from filtered menu with filtered recommendations

### Design Rationale

**Why Advisory vs. Mandatory?**
- Preserves router's autonomy for complex reasoning
- Triage provides guidance based on initial analysis
- Router can override with stronger context-specific reasoning
- Dependencies from failed specialists are hard requirements (must satisfy to proceed)

**Why Filter Recommendations After Context Gathering?**
- Planning specialists (`triage_architect`, `facilitator_specialist`) complete their job
- Prevents router from choosing excluded specialists
- Ensures recommendations match available menu
- Prevents validation failures and default_responder fallbacks

## 3.0 Architectural Best Practices & Lessons Learned

### 3.1 Principle: Match Model Capability to Architectural Role

The `router_specialist` is the most critical reasoning component in the architecture. Assigning a small or less capable model to this role is a significant architectural risk and has been observed to cause pathological failures (runaway generation, context collapse).

**Recommendation:** The `router_specialist` should be run by a capable, instruction-tuned model known for reliable tool use (e.g., Gemini Flash, GPT-3.5-Turbo, or larger). Reserve smaller, more efficient models for more constrained, less critical specialist tasks.

### 3.2 Pattern: Intentional vs. Unproductive Loops

The `GraphOrchestrator` includes a generic loop detection mechanism to halt unproductive cycles (e.g., a sequence like `Router -> Specialist A -> Router -> Specialist A ...`). This mechanism inspects the `routing_history` to prevent the system from getting stuck.

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

The tiered chat architecture is **model-agnostic**. Concrete model bindings are runtime configuration in `user_settings.yaml`:

```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "lmstudio_specialist"  # or "gemini_pro", "claude_sonnet"
  progenitor_bravo_specialist: "lmstudio_specialist"
```

### 4.7 Backward Compatibility

When tiered chat components are NOT configured, the system falls back to single-node `chat_specialist` with no behavior changes.

### 4.8 Related Patterns

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
3.  **Progressive Loop Detection:** Detects both immediate loops (`A -> A -> A`) and 2-step cycles (`A -> B -> A -> B`). Enhanced with stagnation checking to distinguish productive iteration (different outputs) from stuck loops (same output). See §5.4 for details.

### 5.2 Integration Point

The monitor is integrated directly into the `NodeExecutor`'s `create_safe_executor` wrapper. This ensures that **no specialist** can execute if the system is in an invalid state.

```python
# NodeExecutor.create_safe_executor
def safe_executor(state: GraphState) -> Dict[str, Any]:
    # ...
    # Fail-fast if the system is in an invalid state
    self.invariant_monitor.check_invariants(state, stage=f"pre-execution:{specialist_name}")
    # ...
```

### 5.3 Observability

The `InvariantMonitor` is instrumented with LangSmith tracing (`@traceable`). In the LangSmith UI, you will see `InvariantMonitor.check_invariants` calls as "tool" runs within the trace, allowing you to verify that checks are passing (or see exactly why they failed).

### 5.4 Progressive Loop Detection with Stagnation Check

The loop detection distinguishes between:
- **Productive iteration:** Specialist repeats legitimately with different outputs (e.g., downloading file1, file2, file3)
- **Stuck loops:** Specialist repeats with identical output (same error repeated)

**Solution: Three-Check Logic**

The enhanced loop detection implements a progressive verification strategy:

```
CHECK 1: IDENTITY - Is specialist repeated > threshold (3)?
    ↓ YES
CHECK 2: CONFIG - Does specialist allow iteration?
    ↓ YES (allows_iteration=True in config.yaml)
CHECK 3: STAGNATION - Is output hash identical to last execution?
    ↓ YES → KILL FAST (InvariantViolationError)
    ↓ NO → Check max_iterations → ALLOW or KILL
```

**Configuration Example:**

```yaml
# config.yaml
specialists:
  researcher_specialist:
    allows_iteration: true       # Can repeat legitimately
    max_iterations: 20           # Cap for extensive workflows
    detect_stagnation: true      # Kill if same output (stuck)
```

**How It Works:**

1. **Output Hash Tracking:** After each specialist execution, `GraphOrchestrator.safe_executor` computes an MD5 hash of the specialist's output message and stores it in `scratchpad.output_hashes` (last 3 hashes per specialist).

2. **Stagnation Detection:** When a specialist repeats beyond the threshold, the system:
   - Checks if `allows_iteration=True` in config
   - Compares the last 2 output hashes
   - If identical → raises `InvariantViolationError` (stagnation detected)
   - If different → allows execution (productive iteration)

3. **Iteration Cap:** Even with productive iteration, `max_iterations` enforces a safety limit.

**Benefits:**

- ✅ **Eliminates False Positives:** Research workflows (15-20 iterations) work correctly
- ✅ **Preserves Fail-Fast:** Stuck loops still killed in 4 turns (threshold+1)
- ✅ **Zero Breaking Changes:** Non-iterative specialists use standard loop detection
- ✅ **Hardware-Inspired:** MD5 checksum approach mirrors assembly/hardware integrity patterns

**Integration with Menu Filter (ADR-CORE-016):**

Progressive loop detection works as **first-line defense** before the Menu Filter Pattern:

1. **Tier 1a (Progressive Detection):** Allows productive iteration, kills stagnation fast
2. **Tier 1b (Menu Filter):** If stagnation detected, removes specialist from router's menu (P=0)
3. **Tier 2 (Circuit Breaker):** Final HALT if both tiers fail

## 6.0 Pattern: Context Engineering & Faithfulness

**Context:** Traditional RAG systems often fail when users provide ambiguous prompts (e.g., "fix the bug" without specifying the file) or ask questions that require external knowledge not in the model's weights. Models often hallucinate answers in these scenarios.

**Solution:** The system implements a **Context Engineering** phase *before* the main routing loop. This phase analyzes the request, gathers missing context, and enforces "faithfulness" by asking clarification questions instead of guessing.

### 6.1 The Triage Architect

The `triage_architect` is the entry point of the system. It does not answer the user's question. Instead, it produces a `ContextPlan` containing a list of actions:

*   **RESEARCH:** Search the web for real-time info.
*   **READ_FILE:** Read specific files mentioned in the prompt.
*   **LIST_DIRECTORY:** Enumerate directory contents to discover files.
*   **SUMMARIZE:** Compress large context.
*   **ASK_USER:** (Faithfulness Check) Ask the user for clarification if the request is ambiguous.

### 6.2 The Faithfulness Loop (ADR-CORE-018)

If the `triage_architect` determines that the request is ambiguous or impossible to fulfill (e.g., "Fix the function" with no file context), it generates an `ASK_USER` action.

**Workflow:**
1.  **Triage:** Detects ambiguity -> `{"type": "ask_user", "target": "Which file?"}`
2.  **Facilitator:** Executes any automated actions first (READ_FILE, RESEARCH, etc.)
3.  **Dialogue:** Detects remaining `ASK_USER` actions -> calls `interrupt()` to pause graph
4.  **User:** Provides clarification via `/v1/graph/resume` endpoint
5.  **Resume:** Graph continues with user's answer injected into state

This prevents the `router_specialist` from receiving a bad prompt and hallucinating a solution.

**Key Components:**
- `DialogueSpecialist`: Uses LangGraph's `interrupt()` function to pause execution
- `SqliteSaver`/`PostgresSaver`: Checkpointing backends for state persistence
- `/v1/graph/resume` API: Endpoint to continue interrupted workflows

**Configuration:**
```yaml
# user_settings.yaml
checkpointing:
  enabled: true
  backend: "sqlite"  # "sqlite" for dev, "postgres" for production
  sqlite_path: "./data/checkpoints.db"
```

### 6.3 Context Facilitation

If the plan contains valid context-gathering actions (Research/Read/List), the `facilitator_specialist` executes them using MCP (Message-Centric Protocol) to gather the data *before* the main router sees the request. This ensures the router has all necessary context to make an informed decision.

## 7.0 Communication Protocol: MCP (Message-Centric Protocol)

The system uses **MCP** for synchronous, direct service invocation between specialists, replacing the earlier Dossier pattern with a more efficient architecture.

### 7.1 MCP Architecture

**Components:**
- `McpRegistry`: Per-graph-instance service registry (ensures test isolation)
- `McpClient`: Convenience wrapper for making service calls
- `McpRequest`/`McpResponse`: Pydantic schemas with UUID-based distributed tracing
- `ExternalMcpClient`: Manages connections to external containerized services

**Design Principles:**
- Synchronous Python function calls for internal MCP
- Async JSON-RPC via stdio for external containers (ADR-MCP-003)
- Timeout protection (5 seconds default)
- Optional LangSmith tracing integration

### 7.2 External MCP (Containerized Services)

The system supports external MCP servers (Node.js, Docker containers) via `ExternalMcpClient`:

**Key Features:**
- Async communication with containerized MCP servers
- JSON-RPC protocol over stdio
- Fail-fast error handling (Stage 1 implementation)
- LangSmith tracing with configuration toggle
- Docker socket mounting for container management

**Example Configuration:**
```yaml
mcp:
  external_mcp:
    enabled: true
    tracing_enabled: true
    services:
      filesystem:
        enabled: true
        command: "docker"
        args:
          - "run"
          - "-i"
          - "--rm"
          - "-v"
          - "${WORKSPACE_PATH}:/projects"
          - "mcp/filesystem"
          - "/projects"
```

### 7.3 Usage Pattern

```python
# Specialist calling MCP service
result = self.mcp_client.call(
    service_name="file_specialist",
    function_name="read_file",
    path="/path/to/file.txt"
)
```

This pattern enables specialists to invoke services directly without routing through the graph, reducing latency and LLM costs for deterministic operations.

## 8.0 Pattern: Subgraph Architecture (Generate-Critique-Refine)

The system supports tightly-coupled specialist subgraphs that operate independently of the main routing loop. This pattern is exemplified by the Web Builder ↔ Critic subgraph (ADR-CORE-012).

### 8.1 Subgraph Structure

```
Router → web_builder → critic_specialist
            ↑              ↓
            └── REVISE ────┘
                ACCEPT → check_task_completion → END
```

### 8.2 Critical Configuration Requirements

**Three components must align:**

1. **Exclusion from Hub-and-Spoke** - Handled by `CriticLoopSubgraph.get_excluded_specialists()`

2. **Direct Edge** - Wired in `CriticLoopSubgraph.build()`:
   ```python
   workflow.add_conditional_edges("web_builder", self.orchestrator.after_web_builder)
   ```

3. **Config Setting** (`config.yaml`):
   ```yaml
   critic_specialist:
     revision_target: "web_builder"
   ```

### 8.3 Why This Pattern Matters

**Without subgraph:**
- Router hops create 3x overhead
- False loop detection triggers
- Critic's revision recommendations ignored

**With subgraph:**
- Tight refinement loop
- 66% faster execution
- Specialist recommendations respected

## 9.0 Observability & Debugging

The system provides multiple observability layers for debugging and performance analysis:

### 9.1 LangSmith Integration

LangSmith tracing is mandatory for non-trivial workflows:
- Visual trace inspection of workflow execution
- State snapshots at each node
- Error isolation and stack traces
- Performance analysis and timing

**Configuration:**
```bash
# .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=your_project_name
```

### 9.2 Debug Logs

All debug logs are written to `./logs/agentic_server.log`:
- DEBUG level includes graph compilation details
- INFO level shows specialist initialization and routing decisions
- WARNING level captures degraded modes and recoverable errors
- ERROR level logs failures with full stack traces

### 9.3 Archive Reports

The `ArchiverSpecialist` generates workflow completion reports in `./logs/archive/`:
- State snapshots at completion
- Artifact inventories
- Execution path (routing_history)
- Performance metrics

**Common Debugging Workflow:**
1. Check `./logs/agentic_server.log` for errors during startup or execution
2. Review archive reports in `./logs/archive/` for completed workflows
3. Use LangSmith UI for visual trace inspection (retrieve specific trace URLs as needed)

## 10.0 Model-Agnostic Architecture

The architecture maintains strict model-agnosticism through the 3-tier configuration system:

### 10.1 Configuration Tiers

1. **Tier 1 (Secrets):** `.env` - API keys, connection details (git-ignored)
2. **Tier 2 (Architecture):** `config.yaml` - System blueprint, all possible components (committed)
3. **Tier 3 (Implementation):** `user_settings.yaml` - Model bindings, runtime config (git-ignored)

### 10.2 Philosophy

Architecture never depends on specific models. All model bindings are runtime startup configuration in `user_settings.yaml`. This enables:
- Zero-cost development with local models (LM Studio, Ollama)
- Seamless upgrade to API models for production
- Per-specialist model selection (hybrid deployments)
- A/B testing across different model providers

### 10.3 Model-Specific Sampling Parameters

The LMStudio adapter supports pass-through of model-specific sampling parameters via the `parameters` dict. This is critical for models like MoE (Mixture of Experts) that require specific tuning:

```yaml
# user_settings.yaml
llm_providers:
  lmstudio_router:
    type: "lmstudio"
    api_identifier: "openai/gpt-oss-20b-gguf/gpt-oss-20b-mxfp4.gguf"
    parameters:
      temperature: 0.7
      top_p: 0.8      # Nucleus sampling
      top_k: 64       # Top-k sampling
      # Any additional OpenAI-compatible params passed through
```

**Supported Parameters:**
- `temperature`, `max_tokens` - Standard (explicitly handled)
- `top_p`, `top_k` - Sampling params (passed through)
- Any other OpenAI-compatible params - Passed through to the API

The adapter logs extra params on initialization for verification:
```
INITIALIZED LMStudioAdapter... extra_params={'top_p': 0.8, 'top_k': 64}
```
