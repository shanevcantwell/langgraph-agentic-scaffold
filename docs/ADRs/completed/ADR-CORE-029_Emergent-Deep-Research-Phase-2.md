# ADR-CORE-029: Emergent Deep Research Phase 2 (ReActMixin Integration)

**Status:** IMPLEMENTED
**Date:** 2025-12-19
**Implemented:** 2025-12-19 (commit d5cd7ea)
**Depends On:** ADR-CORE-027 (Navigation-MCP), ReActMixin, EMERGENT_PROJECT_SUBGRAPH.md
**Related:** ESM-Foundry Roadmap, DEEP_RESEARCH_CONVENING_DIALECTIC.md

---

## Context

### Phase 1 (Implemented)
- **ProjectContext**: Pydantic state model (goal, knowledge_base, open_questions, state, iteration)
- **ProjectDirector**: LLM specialist that decides next action (SEARCH, BROWSE, COMPLETE)
- **WebSpecialist**: Procedural worker executing atomic tasks
- **EmergentProjectSubgraph**: Graph-level wiring (ProjectDirector ↔ WebSpecialist)

### The Problem
The current graph-level cycling pattern triggers the **2-step cycle invariant**:

```
ProjectDirector → WebSpecialist → ProjectDirector → WebSpecialist → ... → INVARIANT VIOLATION
```

The invariant system (`check_loop_detection`) handles single-specialist loops with `allows_iteration` config, but **2-step cycles have no escape hatch**. After `max_loop_cycles` (default 3) repetitions, the circuit breaker triggers regardless of whether progress is being made.

### Why This Matters
Deep research is inherently iterative:
- Search → analyze results → need more info → search again
- Browse → extract data → find related link → browse again
- This pattern may require 10-20+ cycles for complex topics

---

## Decision

Refactor ProjectDirector to use **ReActMixin** for internal iteration, calling WebSpecialist capabilities via MCP rather than graph routing.

### Architecture Shift

```
BEFORE (Graph-Level Cycling):
  Router → ProjectDirector → WebSpecialist → ProjectDirector → WebSpecialist → ...
  (Each arrow is a graph edge, triggering cycle detection)

AFTER (Internal ReAct Loop):
  Router → ProjectDirector [
    LLM → MCP(search) → LLM → MCP(browse) → LLM → ... → synthesis
  ] → Router
  (Single graph node, loop controlled by max_iterations parameter)
```

### Implementation

```python
from app.src.specialists.base import BaseSpecialist
from app.src.specialists.mixins import ReActMixin, ToolDef, MaxIterationsExceeded
from app.src.interface.project_context import ProjectContext, ProjectState

class ProjectDirector(BaseSpecialist, ReActMixin):
    """
    Emergent Deep Research controller using ReActMixin for internal iteration.

    The LLM decides each iteration whether to:
    - search: Execute web search via MCP
    - browse: Fetch and parse URL content via MCP
    - complete: Synthesize findings and exit loop
    """

    DEFAULT_MAX_ITERATIONS = 20

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Initialize or restore ProjectContext
        project_context = self._get_or_init_context(state)

        # Define available tools (MCP services)
        tools = {
            "search": ToolDef(
                service="web_specialist",
                function="search",
                description="Search the web for information. Returns list of results with title, url, snippet."
            ),
            "browse": ToolDef(
                service="browse_specialist",
                function="browse",
                description="Fetch and parse a URL. Returns page content as text."
            ),
        }

        # Build context-aware prompt
        system_context = self._build_research_prompt(project_context)
        messages = [HumanMessage(content=system_context)]

        try:
            # ReAct loop: LLM decides tool calls until it returns text-only response
            final_response, tool_history = self.execute_with_tools(
                messages=messages,
                tools=tools,
                max_iterations=self._get_max_iterations(),
                stop_on_error=False  # Report errors to LLM for adaptive recovery
            )

            # Update ProjectContext with synthesis
            project_context.update_state(ProjectState.COMPLETE)

            return {
                "messages": [AIMessage(content=final_response)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    "research_trace": [h.model_dump() for h in tool_history],
                    "iterations_used": len(tool_history)
                }
            }

        except MaxIterationsExceeded as e:
            # Graceful degradation: synthesize what we have
            partial_synthesis = self._synthesize_partial(project_context, e.history)

            return {
                "messages": [AIMessage(content=partial_synthesis)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    "research_trace": [h.model_dump() for h in e.history],
                    "max_iterations_exceeded": True,
                    "iterations_used": e.iterations
                }
            }

    def _build_research_prompt(self, context: ProjectContext) -> str:
        """Build the research context prompt for the LLM."""
        return f"""
You are conducting research on: {context.project_goal}

Current Knowledge Base:
{json.dumps(context.knowledge_base, indent=2) if context.knowledge_base else "None yet"}

Open Questions:
{json.dumps(context.open_questions, indent=2) if context.open_questions else "Determine what questions need answering"}

Instructions:
1. Use the 'search' tool to find relevant information
2. Use the 'browse' tool to read specific pages in detail
3. When you have enough information, provide your final synthesis WITHOUT calling any tools

Your synthesis should:
- Answer the original research goal
- Cite sources where relevant
- Note any remaining uncertainties
"""

    def _get_max_iterations(self) -> int:
        """Get max iterations from config or default."""
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _synthesize_partial(self, context: ProjectContext, history: List[ToolResult]) -> str:
        """Generate partial synthesis when max iterations exceeded."""
        # Could use LLM call here for better synthesis
        sources = [h.result.get("url", "unknown") for h in history if h.success and h.result]
        return f"""
Research incomplete (max iterations reached).

Goal: {context.project_goal}

Findings so far:
{json.dumps(context.knowledge_base, indent=2)}

Sources consulted: {len(sources)}

Please refine your research request or increase the iteration limit.
"""
```

### Configuration

```yaml
specialists:
  project_director:
    type: "hybrid"
    prompt_file: "project_director_prompt.md"
    max_iterations: 20  # Research-specific limit
    description: "Emergent deep research controller with iterative tool use"
    tags:
      - "research"
      - "emergent"
```

### Subgraph Simplification

With ReActMixin, `EmergentProjectSubgraph` becomes unnecessary:

```python
# BEFORE: Complex graph-level cycling
workflow.add_conditional_edges("project_director", orchestrator.after_project_director, {...})
workflow.add_conditional_edges("web_specialist", orchestrator.after_web_specialist, {...})

# AFTER: Standard hub-and-spoke (ProjectDirector handles iteration internally)
# No special subgraph wiring needed
```

ProjectDirector becomes a regular specialist that Router can invoke for research tasks, and it handles the entire research loop internally before returning.

---

## Progress Tracking

### Stagnation Detection (Built into ReActMixin)
ReActMixin naturally detects stagnation:
- If LLM keeps calling the same tool with same args → likely stuck
- Tool results are appended to messages → LLM sees repeated failures
- `stop_on_error=False` allows LLM to adapt to failures

### Productive vs Unproductive
The LLM's decision to stop calling tools is the "progress" signal:
- **Productive**: LLM gathers info, then synthesizes (tools → no tools → response)
- **Unproductive**: LLM keeps calling tools without converging (hits max_iterations)

### ProjectContext Evolution
Even though the loop is internal, ProjectContext can still be updated:

```python
def _process_tool_result(self, result: ToolResult, context: ProjectContext):
    """Hook to update context after each tool call (optional enhancement)."""
    if result.success and result.call.name == "search":
        # Add search results to knowledge base
        for item in result.result:
            context.add_knowledge(f"Found: {item['title']} - {item['snippet']}")
```

---

## Consequences

### Positive
1. **Bypasses 2-step cycle invariant** - Single graph node, no cycle detection triggered
2. **Simpler graph** - No special subgraph wiring needed
3. **Natural termination** - LLM decides when research is complete
4. **Graceful degradation** - MaxIterationsExceeded provides partial results
5. **Observable** - `research_trace` artifact captures full tool history
6. **Consistent with ReActMixin pattern** - Reuses proven infrastructure

### Negative
1. **Single model dependency** - All research decisions in one LLM call chain
2. **Context window pressure** - Tool results accumulate in messages
3. **Less observable mid-loop** - No graph-level checkpoints during iteration

### Mitigations
- **Context window**: Summarize tool results before appending (future enhancement)
- **Observability**: `research_trace` artifact provides post-hoc visibility
- **Multi-model**: Could use different models for search decisions vs synthesis (future)

---

## Migration Path

### Phase 2a: Minimal Changes
1. Add ReActMixin to ProjectDirector
2. Register WebSpecialist search/browse as MCP services
3. Remove EmergentProjectSubgraph wiring
4. Test with existing prompts

### Phase 2b: Enhanced Context Management
1. Add mid-loop ProjectContext updates
2. Implement tool result summarization
3. Add stagnation detection hooks

### Phase 2c: Full ESM Integration (Future)
1. Evaluate if full ESM-Foundry needed for HIL research sessions
2. Consider PostgreSQL checkpointing for resume capability
3. Integrate with Convening/HEAP for multi-session research

---

## Testing Strategy

```python
@pytest.mark.integration
def test_project_director_completes_research():
    """Test that ProjectDirector can complete a research task."""
    state = {
        "messages": [HumanMessage(content="What are the top 3 Python web frameworks in 2024?")],
        "artifacts": {},
        "scratchpad": {}
    }

    result = project_director.execute(state)

    # Should have synthesis
    assert result["messages"]
    assert "Flask" in result["messages"][0].content or "Django" in result["messages"][0].content

    # Should have trace
    assert "research_trace" in result["artifacts"]
    assert len(result["artifacts"]["research_trace"]) > 0

    # Should NOT have hit max iterations for simple query
    assert result["artifacts"].get("max_iterations_exceeded") is not True

@pytest.mark.integration
def test_project_director_graceful_degradation():
    """Test that ProjectDirector handles max iterations gracefully."""
    state = {
        "messages": [HumanMessage(content="Write a comprehensive 50-page report on quantum computing")],
        "artifacts": {},
        "scratchpad": {}
    }

    # Use low max_iterations to force degradation
    project_director.specialist_config["max_iterations"] = 3
    result = project_director.execute(state)

    # Should still return something
    assert result["messages"]
    assert result["artifacts"]["max_iterations_exceeded"] is True
```

---

## References

- [ReActMixin](app/src/specialists/mixins/react_mixin.py)
- [EMERGENT_PROJECT_SUBGRAPH.md](docs/EMERGENT_PROJECT_SUBGRAPH.md)
- [ESM-Foundry Roadmap](docs/ADRs/proposed/emergent_state_machine/ROADMAP_Emergent_State_Machine.md)
- [DEEP_RESEARCH_CONVENING_DIALECTIC.md](docs/ADRs/proposed/DEEP_RESEARCH_CONVENING_DIALECTIC.md)
- [invariants.py](app/src/resilience/invariants.py) - Loop detection implementation
