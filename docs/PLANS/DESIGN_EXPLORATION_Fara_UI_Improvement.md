# Design Exploration: Fara-7B Integration for UI Improvement Workflows

**Status:** Exploratory  
**Date:** 2025-12-03  
**Context:** LAS architecture extension for visual verification and UI improvement

---

## 1. Problem Statement

### 1.1 The Integration Testing Gap

LAS currently supports two testing paradigms:

1. **Mocked unit tests** — Fast, cheap, isolated. Verify logic flow but not actual behavior.
2. **Integration tests via graph routing** — Test full specialist execution, but don't verify what users actually see.

The gap: tests can verify that `response.status == "accepted"` but cannot verify that the "accepted" label is visible, clickable, and semantically coherent in the rendered UI.

### 1.2 The prompt-prix Pattern

prompt-prix demonstrates a procedural evaluation approach:
- Fan-out identical prompts to N models
- Collect structured results in Model × Test grid
- Verification is external to the model being tested

This pattern works because evaluation is embarrassingly parallel and comparison-focused. The question: can this extend to visual verification?

### 1.3 The Fara-7B Opportunity

Microsoft's Fara-7B (released late November 2025):
- Pure vision model — sees screenshots, predicts coordinates
- Based on Qwen2.5-VL-7B (same family as current LAS router)
- 16 steps average vs. 41 for UI-TARS on equivalent tasks
- Playwright action primitives: `click(x,y)`, `type()`, `web_search()`, `visit_url()`
- "Critical Points" pattern — trained to pause at irreversible actions
- MIT license, open weights, runs locally on Copilot+ PCs

Key insight: Fara provides visual grounding without requiring frontier API costs.

---

## 2. Use Cases

### 2.1 UI Verification in Integration Tests

After running a LAS specialist through the full pipeline, verify the rendered output:

```python
# After diplomatic consensus flow completes
screenshot = await renderer.capture()
assert await fara.verify_element(screenshot, "AI response containing synthesized answer")
assert await fara.verify_no_errors(screenshot)
```

### 2.2 Visual Regression Testing

Extend prompt-prix grid to include visual verification column:

| Viewport | Response Renders | No Errors | Accessibility |
|----------|------------------|-----------|---------------|
| Desktop  | ✓                | ✓         | ✓             |
| Mobile   | ✓                | ✓         | ❌            |
| Tablet   | ✓                | ❌        | ✓             |

Failed cells become next iteration's input.

### 2.3 UI Improvement Agent

A reasoning model that:
1. Receives UI improvement objective ("make submit button more prominent")
2. Captures current state via Fara
3. Proposes modifications
4. Renders modified code
5. Verifies improvement via Fara
6. Iterates until objective met or max iterations

---

## 3. Architectural Options Considered

### 3.1 Fara as MCP Service (Recommended)

Fara slots cleanly into the existing MCP service layer pattern:

```python
class FaraSpecialist(BaseSpecialist):
    """MCP service for visual verification. NOT routable."""
    
    def register_mcp_services(self, registry: 'McpRegistry'):
        registry.register_service(self.specialist_name, {
            "capture_screenshot": self.capture_screenshot,
            "verify_element": self.verify_element,
            "verify_no_errors": self.verify_no_errors,
            "locate_element": self.locate_element,
            "click": self.click,
            "type_text": self.type_text,
        })
    
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """No-op for MCP-only mode."""
        return {}
```

The Playwright browser pool and Fara-7B model live inside this specialist as managed internal state.

### 3.2 Emergent UIDirector Pattern

Mirrors ProjectDirector/WebSpecialist from EMERGENT_PROJECT_SUBGRAPH:

```
UIDirector (LLM specialist)
    │
    ├─ Analyzes UIContext (goal, current state, feedback history)
    ├─ Issues commands: SCREENSHOT, VERIFY, MODIFY, RENDER
    ├─ Decides when objective is met
    │
    ↓ MCP calls
FaraSpecialist (MCP service)
```

Graph sees: `Router → UIDirector ←→ (internal MCP loop) → Router`

### 3.3 UI Improvement Subgraph

Mirrors Web Builder → Critic (ADR-CORE-012):

```
Router → UIProposer → Renderer → FaraVerifier
            ↑                         ↓
            └──── REVISE ─────────────┘
                  ACCEPT → check_task_completion
```

More observable in LangSmith, but higher routing overhead.

### 3.4 Hybrid: Procedural Runner + LAS Governance

Fast iteration loop runs procedurally (like prompt-prix), invokes LAS governance for approval:

```
┌─────────────────────────────────────────────┐
│         UI Improvement Runner               │
│         (procedural, tool-using)            │
│   [tight loop: assess → propose → verify]   │
└──────────────────────┬──────────────────────┘
                       │ candidate ready
                       ▼
┌─────────────────────────────────────────────┐
│         LAS Governance (optional)           │
│   Arbiter reviews against principles        │
│   [ACCEPT → commit, REVISE → back to loop]  │
└─────────────────────────────────────────────┘
```

---

## 4. The Identified Gap

### 4.1 Current Capabilities

| Pattern | Description | LLM Calls | Iteration |
|---------|-------------|-----------|-----------|
| BatchProcessor | LLM plans once, procedural loop executes | 1 | Procedural |
| ProjectDirector | LLM decides per iteration, graph routes to worker | N | Graph-mediated |
| Web Builder → Critic | Generator and critic as separate nodes | 2 per cycle | Graph-mediated |

### 4.2 What's Missing

**LLM-driven iterative tool use within a single specialist execution.**

The BatchProcessor pattern:
```python
plan = self.llm.invoke("Generate plan")  # ONE LLM call
for item in plan.decisions:               # Procedural loop
    self.mcp_client.call(...)
```

What Fara needs (ReAct-style):
```python
while not done:
    action = self.llm.invoke("What next?", tool_results=last_result)  # LLM per iteration
    if action.type == "VERIFY":
        last_result = self.mcp_client.call("fara", "verify_element", ...)
    elif action.type == "CLICK":
        last_result = self.mcp_client.call("fara", "click", ...)
    elif action.type == "DONE":
        done = True
```

The LLM needs to see Fara's output and decide the next action, repeatedly, within a single graph node.

---

## 5. Proposed Solutions for the Gap

### 5.1 ReAct Mixin for BaseSpecialist

```python
class ReActMixin:
    """Adds iterative tool-use capability to specialists."""
    
    def execute_with_tools(
        self, 
        messages: List, 
        tools: Dict[str, Callable],
        max_iterations: int = 10
    ) -> Tuple[str, List[ToolResult]]:
        """ReAct loop: LLM → tool → LLM → tool → ... → final answer."""
        
        tool_history = []
        
        for i in range(max_iterations):
            response = self.llm_adapter.invoke(
                StandardizedLLMRequest(
                    messages=messages + self._format_tool_history(tool_history),
                    tools=list(tools.keys()),
                )
            )
            
            if response.get("tool_calls"):
                call = response["tool_calls"][0]
                result = tools[call["name"]](**call["args"])
                tool_history.append(ToolResult(call=call, result=result))
            else:
                return response["content"], tool_history
        
        raise MaxIterationsExceeded(tool_history)
```

Usage in a specialist:

```python
class UIImprovementSpecialist(BaseSpecialist, ReActMixin):
    
    def _execute_logic(self, state):
        tools = {
            "screenshot": lambda: self.mcp_client.call("fara", "capture_screenshot"),
            "verify": lambda desc: self.mcp_client.call("fara", "verify_element", description=desc),
            "click": lambda x, y: self.mcp_client.call("fara", "click", x=x, y=y),
            "modify_code": lambda path, content: self.mcp_client.call("file_specialist", "write_file", ...),
        }
        
        final_answer, history = self.execute_with_tools(
            messages=state["messages"],
            tools=tools,
            max_iterations=15
        )
        
        return {
            "artifacts": {"ui_improvement_trace": history},
            "messages": [AIMessage(content=final_answer)]
        }
```

### 5.2 Adapter-Level ReAct Support

Push the loop into the LLM adapter. Some APIs support this natively with function calling.

```python
class LMStudioAdapter(BaseAdapter):
    
    def invoke_with_tools(
        self, 
        request: StandardizedLLMRequest,
        tool_executors: Dict[str, Callable],
        max_iterations: int = 10
    ) -> StandardizedLLMResponse:
        """Execute tool calls until model returns final response."""
        
        messages = request.messages.copy()
        
        for _ in range(max_iterations):
            response = self._raw_invoke(messages, request.tools)
            
            if not response.tool_calls:
                return response
            
            for call in response.tool_calls:
                result = tool_executors[call.name](**call.args)
                messages.append(ToolResultMessage(call_id=call.id, result=result))
        
        raise MaxIterationsExceeded()
```

### 5.3 Graph Routing (Existing Pattern)

Accept routing overhead. Create UIDirector that mirrors ProjectDirector:

```
Router → UIDirector → FaraWorker → UIDirector → FaraWorker → ... → Router
```

More observable in LangSmith (each iteration visible as graph node), but 2 hops per Fara call.

### 5.4 Trade-off Summary

| Approach | LangSmith Visibility | Latency | Complexity | Change Scope |
|----------|---------------------|---------|------------|--------------|
| ReAct mixin | Low (internal loop hidden) | Low | Medium | New mixin |
| Adapter-level | Low (same) | Low | Medium | Adapter changes |
| Graph routing | High (each iteration visible) | Higher | Low | Existing pattern |

---

## 6. Open Questions for Future Exploration

### 6.1 Architectural

1. **Is ReAct general enough for a shared mixin?** Or should it be implemented per-specialist as needed?

2. **Where should the browser pool live?** Inside FaraSpecialist? Separate MCP service? Shared resource?

3. **How does this interact with existing subgraphs?** Could Web Builder → Critic evolve to include visual verification in the critic phase?

4. **Should rendered artifacts be persisted?** Screenshots as evidence in artifacts? Or ephemeral?

### 6.2 Implementation

5. **Fara model hosting:** Same GPU as router (qwen3-vl-30b)? Dedicated instance? Both are Qwen-VL family.

6. **Playwright lifecycle:** Per-request browser context? Persistent pool? Container isolation?

7. **Timeout/circuit breaker:** How to handle Fara inference latency in the ReAct loop? Per-tool timeouts?

8. **Observability:** How to trace ReAct iterations in LangSmith when they're internal to a node?

### 6.3 Use Case Refinement

9. **Primary use case priority:** Integration test verification vs. active UI improvement agent vs. both?

10. **Scope of "UI improvement":** CSS tweaks? Component restructuring? Full page redesign?

11. **Human-in-the-loop:** Where do Critical Points (irreversible action pauses) integrate with LAS governance?

### 6.4 Integration with Existing Work

12. **prompt-prix extension:** Visual verification column in the Model × Test grid?

13. **Latent stream extraction:** Does this relate to the SPEC-pixel-stream-extraction work? Fara as the "VL extraction layer"?

14. **Gemini forensics:** Could Fara-based verification detect UI-level behavioral anomalies?

---

## 7. Recommended Next Steps

### Phase 1: Fara as MCP Service (Foundation)
- Implement FaraSpecialist with basic MCP services
- Playwright browser pool management
- Local Fara-7B inference
- Unit tests for MCP service functions

### Phase 2: Integration Test Extension
- Add visual verification to existing integration tests
- `fara.verify_element()` assertions after specialist execution
- Document patterns for test authors

### Phase 3: ReAct Mixin (If Needed)
- Implement ReActMixin if use cases require iterative tool use
- Start with single specialist (UIImprovementSpecialist or extended WebBuilder)
- Evaluate observability gaps

### Phase 4: Governance Integration
- Connect ReAct loop output to Arbiter review
- Critical Points → LAS governance checkpoints
- Evidence artifacts for audit trail

---

## 8. Related Documents

- `ARCHITECTURE.md` — LAS core architecture
- `MCP_GUIDE.md` — MCP service patterns (§5.1 Interface/Service split, §5.2 Internal iteration)
- `EMERGENT_PROJECT_SUBGRAPH.md` — ProjectDirector/Worker pattern
- `GRAPH_CONSTRUCTION_GUIDE.md` — Web Builder → Critic subgraph (ADR-CORE-012)
- `SPEC-pixel-stream-extraction.md` — Related pixel-layer extraction work
- `BRANCH-01-codec-aware-mvp.md` — Codec-level UI tracking

---

## 9. References

- [Fara-7B Blog Post](https://www.microsoft.com/en-us/research/blog/fara-7b-an-efficient-agentic-model-for-computer-use/)
- [Fara-7B on HuggingFace](https://huggingface.co/microsoft/Fara-7B)
- [Playwright Documentation](https://playwright.dev/)
- [ReAct Paper](https://arxiv.org/abs/2210.03629) — Reasoning + Acting pattern
