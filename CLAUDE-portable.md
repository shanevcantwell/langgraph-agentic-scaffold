# LangGraph Agentic Systems - Portable Architectural Patterns

**Purpose:** Universal patterns and principles for building resilient, production-ready LangGraph agentic systems. Extract these concepts when starting new projects.

---

## Core Architectural Pillars

### Pillar 1: Aggressive Resilience
Zero-tolerance for silent failures. Fail-fast validation, self-correction signals, circuit breakers, system-wide invariant monitoring. **The system must fail loudly and predictably when it cannot self-correct.**

**Key Patterns:**
- Fail-fast startup validation (critical components check)
- Route validation before execution (allowed_destinations)
- Circuit breakers with invariant monitoring
- Progressive resilience (Tier 1-4 error handling)

### Pillar 2: Explicit State as Control Plane
Move from LLM inference to structured data directing the system deterministically. State-mediated communication, routing plans, declarative guardrails.

**Key Patterns:**
- Scratchpad for ephemeral communication
- Artifacts for structured outputs
- Messages for permanent history
- State hygiene (never pollute root state)

### Pillar 3: Hybrid Routing Engine
Multi-stage decision architecture:
- **Procedural**: Deterministic pattern matching for trivial tasks
- **Declarative**: State-based policy enforcement
- **Planned**: Strategic fallback on failure
- **Probabilistic**: LLM reasoning as escalation path

### Pillar 4: Professionalized Platform & Tooling
Mature infrastructure, observability, service-oriented deployment, reusable components.

**Key Patterns:**
- LangSmith tracing (mandatory for non-trivial workflows)
- Centralized test fixtures
- Docker Compose for service orchestration
- Model-agnostic architecture

---

## Critical Design Patterns

### 1. State Management for Parallel Execution (CRITICAL)

**Problem:** Parallel nodes in LangGraph can cause 78% token waste if messages are duplicated.

**Solution:**
- ✅ **Parallel nodes (fan-out) write ONLY to `artifacts`, NEVER to `messages`**
- ✅ **Join nodes (fan-in) read artifacts and write to `messages`**
- ✅ Enables proper cross-referencing in conversation history
- ✅ Prevents token waste in multi-turn conversations

**Example:**
```python
# CORRECT: Parallel nodes write to artifacts
def parallel_specialist(state):
    return {
        "artifacts": {
            "my_specialist_output": result
        }
        # NO messages key!
    }

# CORRECT: Join node consolidates artifacts → messages
def join_specialist(state):
    artifacts = state["artifacts"]
    combined_result = synthesize(
        artifacts["specialist_a_output"],
        artifacts["specialist_b_output"]
    )
    return {
        "messages": [AIMessage(content=combined_result)]
    }
```

### 2. Graph Wiring for Parallel Execution

**Problem:** LangGraph needs explicit syntax to wait for multiple predecessors.

**Solution:**
```python
# CORRECT: Array syntax tells LangGraph to wait for BOTH
workflow.add_edge(["node_a", "node_b"], "join_node")

# INCORRECT: Join executes twice (once per predecessor)
workflow.add_edge("node_a", "join_node")
workflow.add_edge("node_b", "join_node")
```

### 3. Centralized Completion Sequence

**Problem:** Specialists terminating graph directly skip final housekeeping.

**Solution:** 3-stage mandatory termination:
1. Specialist signals `task_is_complete: True`
2. `EndSpecialist` synthesizes response and performs cleanup
3. Router sees completion signal → routes to END node

**Benefits:**
- Final archival/logging always executes
- Consistent termination behavior
- State cleanup guaranteed

### 4. Loop Management

**Intentional Loops (Good):**
```python
# Generate → Critique → Generate subgraph
def critique_decision(state):
    if critique_passed:
        return "ACCEPT"  # Exit loop
    else:
        return "REVISE"  # Continue loop

workflow.add_conditional_edges(
    "critic_specialist",
    critique_decision,
    {
        "ACCEPT": "end_specialist",
        "REVISE": "web_builder"  # Loop back
    }
)
```

**Unproductive Loops (Bad):**
- Router → Specialist → Router → Specialist (no progress)
- Detect via `routing_history` inspection
- Use loop detection invariants (threshold-based)

### 5. Subgraph Patterns (Direct Edges for Tight Loops)

**Problem:** Router hops in refinement loops create 3x overhead and trigger false loop detection.

**Solution:** Direct edges for Generate-Critique-Refine patterns:
```python
# Exclude refinement specialist from hub-and-spoke routing
excluded_specialists = ["web_builder"]

# Add direct edge (bypasses router)
workflow.add_edge("web_builder", "critic_specialist")

# Config specialist for revision target
critic_specialist:
  revision_target: "web_builder"
```

**Benefits:**
- 66% faster execution
- No false loop detection
- Specialist recommendations respected

### 6. Virtual Coordinator Pattern

**Problem:** How to transparently upgrade single-node to multi-node subgraph?

**Solution:** Separation of WHAT vs. HOW:
- **Router decides WHAT**: "Need chat capability"
- **Orchestrator decides HOW**: "Use tiered chat subgraph vs. single specialist"

**Benefits:**
- Transparent complexity management
- Graceful degradation (fallback to single specialist)
- No routing logic changes

### 7. Progressive Loop Detection with Stagnation Check

**Problem:** Cannot distinguish productive iteration from stuck loops.

**Solution:** Three-Check Logic:
```
CHECK 1: IDENTITY - Is specialist repeated > threshold?
    ↓ YES
CHECK 2: CONFIG - Does specialist allow iteration?
    ↓ YES (allows_iteration=True)
CHECK 3: STAGNATION - Is output identical to last execution?
    ↓ YES → KILL FAST (stuck loop detected)
    ↓ NO → CHECK max_iterations → ALLOW or KILL
```

**Implementation:**
- Track MD5 hashes of specialist outputs (last 3)
- Compare hashes to detect identical outputs
- Config-driven iteration allowance per specialist

---

## Configuration System (3-Tier)

**Tier 1 (Secrets):** `.env`
- API keys, connection strings
- Git-ignored

**Tier 2 (Architecture):** `config.yaml`
- System blueprint, all possible components
- Specialist configurations, routing rules
- Committed to git

**Tier 3 (Implementation):** `user_settings.yaml`
- Model bindings, runtime config
- Git-ignored (local overrides)

**Model-Agnostic Philosophy:**
- Architecture NEVER depends on specific models
- All model bindings in user_settings.yaml
- Enables zero-cost development with local models
- Seamless upgrade to API models

---

## State Management Rules

### State Structure
```python
class GraphState(TypedDict):
    messages: List[BaseMessage]       # Permanent conversation history
    artifacts: Dict[str, Any]         # Structured outputs between specialists
    scratchpad: Dict[str, Any]        # Ephemeral communication data
    routing_history: List[str]        # Loop detection
    turn_count: int                   # Circuit breaker
    task_is_complete: bool            # Completion signal
```

### State Hygiene Rules
1. **Scratchpad**: Transient specialist communication (cleared after routing)
2. **Artifacts**: Structured outputs for consumption by other specialists
3. **Messages**: LangChain Message objects ONLY (permanent history)
4. **Never pollute root state** with specialist-specific fields
5. **Parallel nodes**: Write to artifacts, not messages
6. **Join nodes**: Read artifacts, write to messages

---

## LLM Adapter Contract

**Problem:** Different LLM providers format responses differently.

**Solution:** All adapters MUST use fallback helper:
```python
def _robustly_parse_json_from_text(text: str) -> dict:
    """
    Handles provider-specific formatting idiosyncrasies.
    Prevents brittle parsing failures across LLM providers.
    """
    # Try standard JSON parse
    # Fall back to regex extraction
    # Handle common malformations
```

**Verified by:** Contract tests in `test_adapter_contracts.py`

---

## Testing Mandates

1. **Use centralized fixtures** for core components
   - Prevents architectural drift
   - Ensures test suite maintainability

2. **MUST NOT create local mocks** for:
   - ConfigLoader
   - AdapterFactory
   - LLM adapters
   - State factory

3. **Test-Driven Validation:**
   - All architectural assumptions validated by tests
   - No untested critical paths

---

## Observability Requirements

### LangSmith Integration (Mandatory)
```bash
# .env configuration
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your_key>
LANGCHAIN_PROJECT=<project_name>
```

**Benefits:**
- Visual tracing of workflow execution
- State inspection at each node
- Error isolation and debugging
- Performance analysis

**FastAPI Integration:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Flush buffered traces before exit
    await flush_langsmith_traces()
```

---

## Fail-Fast Validation

### Startup Validation
```python
# config.yaml
critical_specialists:
  - router_specialist
  - end_specialist
  - chat_specialist

# Application startup
def validate_critical_specialists(config, loaded_specialists):
    missing = set(config.critical_specialists) - set(loaded_specialists.keys())
    if missing:
        raise StartupValidationError(
            f"Critical specialists failed to load: {missing}"
        )
```

### Route Validation
```python
# Build allowed destinations set at compile time
allowed_destinations = {name for name in specialists if name != "router"}

# Validate before execution
def route_to_next_specialist(next_specialist: str):
    if next_specialist not in allowed_destinations:
        raise WorkflowError(
            f"Invalid routing target: '{next_specialist}'. "
            f"Allowed: {sorted(allowed_destinations)}"
        )
```

---

## Progressive Resilience (4-Tier Error Handling)

**Tier 1:** Tactical retry with corrective instruction
- N=2 attempts with specific guidance
- "Your previous output had unmatched brackets. Please fix."

**Tier 2:** Heuristic repair
- Programmatic fixes (bracket balancing, quote escaping)
- Deterministic corrections

**Tier 3:** Escalated technical recovery
- Specialized sub-workflow for complex repairs
- Route to error_handler_specialist

**Tier 4:** Strategic oversight
- Longitudinal trend analysis via telemetry
- Identify systemic issues requiring architectural changes

**Key Distinction:**
- Syntactic faults (Tiers 1-3): Parsing/formatting errors
- Semantic failures: Logic/reasoning errors (requires different handling)

---

## Universal Principles ("Keep in Mind")

### 1. Fail-Fast Philosophy
Silent failures are unacceptable. Every error must be loud, explicit, and immediately actionable.

### 2. State Hygiene
- Scratchpad is transient
- Artifacts are structured outputs
- Messages are permanent history
- Never pollute root state with specialist-specific fields

### 3. Model-Agnostic Architecture
- Never hardcode model dependencies
- All bindings in user_settings.yaml
- Design for smallest viable model

### 4. Separation of Concerns
- **Router**: Decides WHAT (capability needed)
- **Orchestrator**: Decides HOW (implementation)
- **GraphBuilder**: Defines structure (compile-time)
- **GraphOrchestrator**: Executes decisions (runtime)

### 5. Observable by Default
- LangSmith tracing is mandatory
- All state transitions must be traceable
- Log liberally at DEBUG level

### 6. Test-Driven Validation
All architectural assumptions validated by passing automated tests.

### 7. Strategic Deferral is OK
Pragmatic sequencing beats premature optimization. Defer complex patterns until infrastructure matures.

### 8. Building for the Future
Every decision impacts scalability. Consider:
- Will this pattern scale to 10x specialists?
- Does this support persistent state?
- Can this handle failure gracefully?

---

## Common Pitfalls & Solutions

### Pitfall 1: Parallel Execution Token Waste
**Symptom:** Message list grows 2x for every parallel execution
**Solution:** Parallel nodes → artifacts, join nodes → messages

### Pitfall 2: Subgraph Loop Detection False Positives
**Symptom:** Generate-Critique loops trigger loop detection
**Solution:** Direct edges + excluded_specialists configuration

### Pitfall 3: Silent Routing Failures
**Symptom:** Infinite loops from invalid destinations
**Solution:** Route validation with allowed_destinations set

### Pitfall 4: LLM Response Parsing Brittleness
**Symptom:** Different providers break parsing
**Solution:** Robust parse helper with fallback strategies

### Pitfall 5: Missing Final Housekeeping
**Symptom:** Archival/logging skipped on early termination
**Solution:** Centralized completion sequence (3-stage)

---

## Debugging Workflow

### 1. Check Application Logs
```bash
tail -f ./logs/app.log | grep -E "(ERROR|WARNING)"
```

### 2. Inspect LangSmith Traces
- Visual graph execution
- State at each node
- Error stack traces

### 3. Review State Snapshots
```python
logger.debug(f"State after {node_name}: {json.dumps(state, indent=2)}")
```

### 4. Verify Configuration
```bash
# Ensure critical specialists loaded
grep "Loaded specialist:" ./logs/app.log

# Verify routing configuration
grep "allowed_destinations" ./logs/app.log
```

---

## When to Use These Patterns

### ✅ Use Parallel Execution When:
- Multiple independent operations needed
- Results can be synthesized later
- No inter-dependency between operations

### ✅ Use Direct Edges When:
- Tight refinement loop (Generate-Critique-Refine)
- No need for router decision
- Performance critical

### ✅ Use Virtual Coordinator When:
- Need transparent complexity upgrade
- Want graceful degradation
- Separation of WHAT vs. HOW important

### ✅ Use Progressive Loop Detection When:
- Legitimate iteration possible (research workflows)
- Need to distinguish progress from stagnation
- Multiple file operations expected

---

## Quick Reference: State Management

```python
# ✅ CORRECT: Parallel node writes artifacts
def specialist_a(state: GraphState) -> dict:
    return {
        "artifacts": {
            "specialist_a_result": compute_result()
        }
    }

# ✅ CORRECT: Join node reads artifacts, writes messages
def synthesizer(state: GraphState) -> dict:
    result_a = state["artifacts"]["specialist_a_result"]
    result_b = state["artifacts"]["specialist_b_result"]

    combined = synthesize(result_a, result_b)

    return {
        "messages": [AIMessage(content=combined)]
    }

# ❌ INCORRECT: Parallel node writes messages
def specialist_a(state: GraphState) -> dict:
    return {
        "messages": [AIMessage(content=compute_result())]
        # This duplicates messages in conversation history!
    }

# ✅ CORRECT: Scratchpad for ephemeral coordination
def triage(state: GraphState) -> dict:
    return {
        "scratchpad": {
            "recommended_specialists": ["specialist_a", "specialist_b"]
            # Router reads this, then cleared after routing
        }
    }
```

---

## License

These patterns are provided as-is for building production LangGraph systems. Adapt freely to your project's needs.
