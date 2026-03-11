# ADR: CORE-CHAT-002.2 - Virtual Coordinator Pattern for Tiered Chat Routing

**Status:** Completed

**Prerequisite:** CORE-CHAT-002

**Context:**

CORE-CHAT-002 introduces a tiered chat subgraph where routing to "chat_specialist" should trigger parallel execution of ProgenitorAlpha and ProgenitorBravo specialists. This raises an architectural question: **What should "chat_specialist" actually be in the graph structure?**

The router's LLM is trained to select "chat_specialist" for conversational queries. However, with the tiered chat subgraph, we need the router's decision to trigger a fan-out to multiple specialists in parallel. This creates a semantic gap between what the router "thinks" it's routing to and what actually executes.

## The Problem

**Semantic Gap:**
- Router LLM chooses "chat_specialist" as the appropriate specialist for a query
- But "chat_specialist" (single-perspective) is being replaced by a multi-specialist subgraph
- How do we bridge this gap without breaking the router's mental model?

**Graph Constraints:**
- LangGraph conditional edges return node names (str) or lists of node names (list[str]) for parallel execution
- All edge destinations must be valid graph nodes
- The router's tool schema lists available specialists by name

## Decision Options

### Option A: Virtual Coordinator (Router-Level Interception)

**Implementation:**
```python
# In GraphOrchestrator.route_to_next_specialist()
if next_specialist == "chat_specialist":
    if tiered_chat_enabled:
        return ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]  # Fan-out
    else:
        return "chat_specialist"  # Fallback to single specialist
```

**Graph Structure:**
- `chat_specialist` appears in config.yaml but is NOT added as a graph node (when tiered chat enabled)
- `chat_specialist` IS in the router's tool schema (router can choose it)
- Routing decision is intercepted at orchestration level and transformed to parallel execution

**Pros:**
- Clean configuration - router description remains simple ("chat_specialist for Q&A")
- Backward compatible - if tiered chat disabled, regular chat_specialist works
- Router LLM's mental model unchanged - still chooses "chat_specialist"
- Graceful degradation built-in (fallback to single specialist if subgraph incomplete)

**Cons:**
- "Magic" interception - not obvious from graph structure that chat_specialist → fan-out
- chat_specialist exists in config but not always in graph (confusing for debugging)
- Semantic mismatch between router's choice and actual execution
- LangSmith traces may show confusing routing_history

### Option B: Real Coordinator Node

**Implementation:**
- Keep `chat_specialist` as a real graph node
- Make it a procedural coordinator that explicitly triggers the fan-out
- ChatSpecialist._execute_logic() returns special state that triggers parallel routing

**Graph Structure:**
```
Router → ChatSpecialist (coordinator) → [Alpha, Bravo] → Synthesizer
```

**Pros:**
- All nodes are real - no "virtual" specialists
- Explicit in graph structure - clear from code what's happening
- ChatSpecialist could do pre-processing (filter, validate, decide if tiered needed)
- LangSmith traces show actual node execution

**Cons:**
- Extra node in graph (adds latency, even if minimal)
- ChatSpecialist needs LLM adapter OR becomes procedural-only (loses single-chat capability)
- More complex to implement - requires special return value or state flag
- Less clear where fan-out logic lives (coordinator vs orchestrator)

### Option C: Router Knows Internal Architecture

**Implementation:**
- Remove chat_specialist entirely from router tool choices
- Router directly chooses `tiered_chat` or `single_chat` or individual progenitors
- Expose internal architecture to router's decision-making

**Graph Structure:**
```
Router → (chooses) → "tiered_chat" → [Alpha, Bravo] → Synthesizer
                  OR → "single_chat" → DefaultChat
```

**Pros:**
- Most explicit - router makes informed choice about multi-perspective vs single
- No semantic gap - router knows exactly what will execute
- Flexibility - router could choose single progenitor if appropriate

**Cons:**
- Couples router to internal implementation details (violates encapsulation)
- Complicates router tool schema (more options to choose from)
- Breaks abstraction - router shouldn't care HOW chat is implemented
- Makes future refactoring harder (changes ripple to router prompt)

## Recommendation: Option A (Virtual Coordinator)

**Rationale:**

1. **Separation of Concerns:**
   - Router's job: "What capability does the user need?" → "chat"
   - Orchestrator's job: "How do we provide chat?" → "fan-out to progenitors"
   - This separation is architecturally sound

2. **Backward Compatibility:**
   - If tiered chat is disabled (config), regular chat_specialist works seamlessly
   - No changes needed to router prompt or tool schema
   - User can toggle between single and multi-perspective via config

3. **Progressive Enhancement:**
   - Single-perspective chat → Multi-perspective chat is an internal improvement
   - Router doesn't need to know implementation details
   - Future: Could add "chat_specialist_simple" for truly single-perspective queries

4. **Precedent in Codebase:**
   - Similar pattern exists with EndSpecialist (hybrid coordinator)
   - Critical specialists (router, end, archiver) already have special treatment
   - Virtual coordination is an established pattern

5. **Observability:**
   - LangSmith traces will show: "Routing to chat_specialist" → parallel execution visible
   - Archive Report includes routing_history and response_mode
   - Logs clearly indicate "Chat routing detected - fanning out"

## Implementation Details

### Router Configuration (graph_builder.py)
```python
excluded_from_router = [
    CoreSpecialist.ROUTER.value,
    "progenitor_alpha_specialist",   # Internal to subgraph
    "progenitor_bravo_specialist",   # Internal to subgraph
    "tiered_synthesizer_specialist"  # Internal to subgraph
]
# chat_specialist remains visible to router
```

### Graph Node Addition (graph_builder.py)
```python
if has_tiered_chat and name == "chat_specialist":
    logger.info(f"Skipping {name} node - tiered chat subgraph enabled")
    continue  # Don't add chat_specialist as a node
```

### Conditional Edge Destinations (graph_builder.py)
```python
destinations = {name: name for name in self.specialists if name != router_name}
if has_tiered_chat and "chat_specialist" in destinations:
    del destinations["chat_specialist"]  # Remove non-existent node
    # Progenitors already in destinations (they're real nodes)
```

### Orchestration Interception (graph_orchestrator.py)
```python
if next_specialist == "chat_specialist":
    if tiered_chat_enabled:
        logger.info("Chat routing detected - fanning out to parallel progenitors")
        return ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]
    else:
        logger.warning("Tiered chat subgraph incomplete - falling back")
        return "chat_specialist"  # Fallback to single (if node exists)
```

## Alternative Future Patterns

If this pattern proves problematic, we can migrate to:

### Pattern 1: Intent-Based Routing
Router distinguishes between "simple_chat" and "complex_chat":
- simple_chat → single specialist
- complex_chat → tiered subgraph

### Pattern 2: Subgraph as First-Class Entity
LangGraph supports nested graphs - could make tiered chat a proper subgraph:
```python
chat_subgraph = StateGraph(GraphState)
# Add progenitors and synthesizer to subgraph
workflow.add_node("chat_specialist", chat_subgraph.compile())
```

### Pattern 3: Dynamic Routing Function
Instead of interception, make the conditional edge itself fan-out-aware:
```python
def dynamic_chat_router(state):
    if should_use_tiered(state):
        return ["alpha", "bravo"]
    else:
        return "chat_specialist"
```

## Monitoring & Observability

To mitigate the "magic" concern:

1. **Logging:**
   - Log at INFO level when interception occurs
   - Include both what router chose and what actually executes

2. **LangSmith:**
   - routing_history will show actual specialists executed
   - Message names will indicate progenitors ran

3. **Archive Report:**
   - Include response_mode: "tiered_full", "tiered_alpha_only", etc.
   - Document when degraded mode was used

4. **Documentation:**
   - DEVELOPERS_GUIDE.md should explain virtual coordinator pattern
   - Add ASCII diagram showing actual execution flow

## Risks & Mitigations

**Risk 1: Confusing Debugging**
- *Mitigation:* Clear logging, LangSmith instrumentation, this ADR

**Risk 2: Future LangGraph Changes**
- *Mitigation:* Pattern is based on documented conditional edge behavior

**Risk 3: Unclear System Behavior**
- *Mitigation:* Comprehensive integration tests showing actual flow

## Success Criteria

1. Router can choose "chat_specialist" via normal tool calling
2. When tiered chat enabled, parallel execution occurs automatically
3. When tiered chat disabled, single chat_specialist works as before
4. LangSmith traces clearly show actual execution path
5. No graph compilation errors or edge resolution failures

## Related ADRs

- CORE-CHAT-002: Tiered Chat Subgraph (Fan-Out) - parent ADR
- CORE-CHAT-002.1: Graceful Degradation Strategy - error handling
- CORE-CHAT-003: Diplomatic Chat Subgraph (Adversarial) - will use same pattern

**Date:** 2025-11-05
**Decision:** Approved - using Virtual Coordinator pattern (Option A)
