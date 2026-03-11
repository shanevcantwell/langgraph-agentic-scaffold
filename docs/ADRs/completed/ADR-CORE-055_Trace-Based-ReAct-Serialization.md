# ADR-CORE-055: Trace-Based ReAct Serialization

**Explore Target:** `ReAct loop message construction in react_mixin.py, how ProjectDirector builds task prompts, and how adapters serialize messages for providers`

**Status:** Completed (2026-02-01)
**Date:** 2026-01-30
**Deciders:** Shane
**Context:** ReAct loop loses LLM decision context between iterations
**Supersedes:** N/A
**Relates To:** ADR-CORE-051 (Config-Level MCP Tool Binding), ADR-ROADMAP-001 (Facilitator Evolution), Issue #88

---

## Context

### The Problem

Issue #88: PROJECT_DIRECTOR reads files repeatedly but never calls `move_file`. The LLM stays in "investigation mode" and synthesizes "I found apple, zebra, banana" without executing the requested file moves.

### Root Cause Analysis

The ReAct loop in `react_mixin.py` has a fundamental bug in message chain construction.

**Current message flow (broken):**
```
Iteration 1: System + Human(goal) → LLM returns tool_calls
Iteration 2: System + Human(goal) + ToolMessage("apple") → LLM returns tool_calls
Iteration 3: System + Human(goal) + ToolMessage("apple") + ToolMessage("zebra") → LLM synthesizes
```

**Expected message flow (standard function calling):**
```
Iteration 1: System + Human(goal) → LLM returns tool_calls
Iteration 2: System + Human(goal) + AIMessage(tool_calls=[read_file]) + ToolMessage("apple") → LLM returns tool_calls
Iteration 3: System + Human(goal) + AIMessage(tool_calls=[read_file]) + ToolMessage("apple") + AIMessage(tool_calls=[read_file]) + ToolMessage("zebra") → LLM continues
```

**The bug:** After the LLM returns `tool_calls`, we execute the tools and append `ToolMessage` results, but we **never append the `AIMessage`** that contained the tool_calls. The LLM's decision is lost.

**Code location:** `react_mixin.py:366-410`
```python
# Line 358: Extract tool_calls from response
tool_calls = response.get("tool_calls", [])

# Line 366-410: Execute each tool and append ToolMessage
for tc in tool_calls:
    # ... execute tool ...
    result = self._execute_tool(tool_call, tools, stop_on_error, successful_paths)
    tool_history.append(result)
    # ... stagnation detection ...
    working_messages.append(self._format_tool_result_message(result))  # Only ToolMessage!
    # BUG: AIMessage with tool_calls is never appended
```

### Impact

Without AIMessage, each iteration is **reasoning from scratch** with orphaned tool results:

```
LLM sees: "Goal: sort files. Here's tool output: 'apple'. What now?"
LLM doesn't see: "I called read_file(fruit.txt) because I need to understand contents"
```

The LLM has no persistent reasoning chain. It doesn't remember *why* it called those tools or what the overall plan was. From its perspective, information just appears. The rational response is "I have the information, task complete" — which is exactly the observed behavior.

### Architectural Context

In Aug/Sep 2025, `HumanMessage`/`AIMessage` were intentionally pushed out of graph-level orchestration:
- GraphState uses `List[BaseMessage]` (abstract type)
- Specialists communicate via `artifacts` and `scratchpad`, not message manipulation
- LangSmith still shows "HUMAN"/"AI" because underlying LangChain types leak through observability

**The violation:** `react_mixin.py` uses concrete LangChain types internally:
- Imports `AIMessage`, `ToolMessage` from `langchain_core.messages`
- Callers like ProjectDirector construct `HumanMessage(content=research_prompt)`

This mixes graph-level concepts with specialist-internal concerns.

---

## Decision

Refactor `execute_with_tools()` to use **trace-based serialization** instead of message accumulation.

### Key Changes

1. **Interface:** Accept `task_prompt: str` instead of `messages: List[BaseMessage]`
2. **Internal trace:** Maintain `List[ReActIteration]` as the canonical record
3. **Serialization:** Rebuild messages fresh each iteration via `_serialize_for_provider()`
4. **No LangChain types in callers:** Specialists pass strings, not message objects

### Relationship to ADR-ROADMAP-001 (Facilitator Evolution)

This abstraction is designed to work with the Facilitator vision where Facilitator becomes the bidirectional context gatekeeper.

**The ReAct loop is the execution primitive.** It handles linear iteration for a single task:
```
list → read → move → read → move → done
```

**Orchestration strategy is a separate concern.** For research (the original ProjectDirector use case), you need recursive/branching behavior:
```
search(topic) → browse(result_1) →
  ├── deep_dive(subtopic_a) → search → browse → ...
  └── deep_dive(subtopic_b) → search → browse → ...
```

This recursion doesn't belong inside the ReAct loop. When Facilitator is fully realized:

1. **Linear task:** Facilitator → single specialist call → trace back → done
2. **Research task:** Facilitator → specialist call → trace back → Facilitator inspects trace, spawns new tasks → specialist calls → ... → synthesis

**The specialist becomes a pure function:** `(task, tools) → trace`

This means:
- `SpecialistTask` (goal + context from Facilitator) goes IN
- `SpecialistTrace` (iterations + final response) comes OUT
- Facilitator owns the strategy (when to recurse, branch, or synthesize)
- Facilitator can inspect traces for completion checking (Phase 1 of ADR-ROADMAP-001)

The trace-based abstraction enables this future without requiring changes to the specialist interface later.

### New Interface

```python
# react_mixin.py
def execute_with_tools(
    self,
    task_prompt: str,           # Built from artifacts, not messages
    tools: Dict[str, ToolDef],
    max_iterations: int = 10,
    stop_on_error: bool = False,
) -> Tuple[str, List[ReActIteration]]:
    """
    Execute a ReAct loop with the given tools.

    Args:
        task_prompt: The task description (built from state/artifacts)
        tools: Dict mapping tool names to ToolDef objects
        max_iterations: Maximum iterations before stopping
        stop_on_error: If True, raise on first tool error

    Returns:
        Tuple of (final_response: str, trace: List[ReActIteration])
    """
    trace: List[ReActIteration] = []

    for iteration in range(max_iterations):
        # Serialize rebuilds messages fresh each iteration
        messages = self._serialize_for_provider(
            system=self.system_prompt,
            goal=task_prompt,
            trace=trace
        )

        request = StandardizedLLMRequest(
            messages=messages,
            tools=self._build_tool_schemas(tools) if tools else None,
        )

        response = self.llm_adapter.invoke(request)
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            # No tool calls = final response
            return response.get("text_response", ""), trace

        # Execute tools and record in trace
        for tc in tool_calls:
            tool_call = ToolCall(
                id=tc.get("id", f"call_{iteration}"),
                name=tc.get("name", ""),
                args=tc.get("args", {})
            )
            result = self._execute_tool(tool_call, tools, stop_on_error)

            trace.append(ReActIteration(
                iteration=iteration,
                tool_call=tool_call,
                observation=str(result.result) if result.success else f"Error: {result.error}",
                success=result.success
            ))

            # Stagnation detection uses trace
            if self._check_stagnation(trace):
                raise StagnationDetected(...)

    raise MaxIterationsExceeded(max_iterations, trace)
```

### New Types

```python
# react_mixin.py (or new file: app/src/specialists/mixins/react_types.py)
from pydantic import BaseModel
from typing import Optional

class ReActIteration(BaseModel):
    """A single iteration in the ReAct loop - the canonical trace record."""
    iteration: int
    tool_call: ToolCall
    observation: str
    success: bool
    thought: Optional[str] = None  # If LLM provides reasoning text with tool call


# Note: ToolCall and ToolResult already exist, ReActIteration replaces ToolResult
# in the return type since it captures both the call and result together.
```

### Serialization Method

```python
def _serialize_for_provider(
    self,
    system: str,
    goal: str,
    trace: List[ReActIteration]
) -> List[BaseMessage]:
    """
    Convert task prompt and trace into provider-ready message list.

    This is the ONLY place LangChain message types are constructed.
    """
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    messages = [HumanMessage(content=goal)]

    for step in trace:
        # AIMessage with tool_calls
        ai_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": step.tool_call.id,
                "name": step.tool_call.name,
                "args": step.tool_call.args
            }]
        )
        messages.append(ai_msg)

        # ToolMessage with result
        tool_msg = ToolMessage(
            content=step.observation,
            tool_call_id=step.tool_call.id,
            name=step.tool_call.name
        )
        messages.append(tool_msg)

    return messages
```

### Updated Caller (ProjectDirector)

```python
# project_director.py
from langchain_core.messages import AIMessage  # Only for return value

class ProjectDirector(BaseSpecialist):

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        project_context = self._get_or_init_context(state)

        tools = {
            "list_directory": ToolDef(...),
            "read_file": ToolDef(...),
            "move_file": ToolDef(...),
            # ...
        }

        # Build task prompt from artifacts (string, not messages)
        task_prompt = self._build_research_prompt(project_context, state)

        try:
            final_response, trace = self.execute_with_tools(
                task_prompt=task_prompt,  # String, not HumanMessage
                tools=tools,
                max_iterations=self._get_max_iterations(),
                stop_on_error=False
            )

            return {
                "messages": [AIMessage(content=final_response)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    "research_trace": [step.model_dump() for step in trace],
                    "iterations_used": len(trace),
                    "research_status": "complete"
                }
            }

        except StagnationDetected as e:
            # ... handle stagnation ...

        except MaxIterationsExceeded as e:
            # ... handle max iterations ...
```

---

## Implementation

### Files to Modify

| File | Changes |
|------|---------|
| `app/src/specialists/mixins/react_mixin.py` | New interface, `ReActIteration` type, `_serialize_for_provider()` |
| `app/src/specialists/project_director.py` | Update to pass `task_prompt` string, remove `HumanMessage` import |
| `app/tests/unit/test_react_mixin.py` | Update tests for new interface |

### Migration Steps

1. Add `ReActIteration` model to `react_mixin.py`
2. Add `_serialize_for_provider()` method
3. Update `execute_with_tools()` signature and implementation
4. Update `ProjectDirector._execute_logic()` to use new interface
5. Update unit tests
6. Run integration tests to verify file sorting works

### Backward Compatibility

**Breaking change:** The `execute_with_tools()` signature changes from:
```python
def execute_with_tools(messages: List[BaseMessage], ...) -> Tuple[str, List[ToolResult]]
```
to:
```python
def execute_with_tools(task_prompt: str, ...) -> Tuple[str, List[ReActIteration]]
```

Only one caller exists (`ProjectDirector`), so migration is straightforward.

---

## Consequences

### Positive

- **Fixes Issue #88:** AIMessage with tool_calls is now included in every iteration
- **Clean architecture:** LangChain types pushed to serialization boundary
- **No message accumulation:** Trace is canonical, messages rebuilt fresh each iteration
- **Better observability:** `ReActIteration` is a Pydantic model, easy to serialize to archives
- **Aligns with Aug/Sep 2025 intent:** Specialists don't manipulate LangChain message types directly

### Negative

- **Breaking change:** Callers must update to new signature
- **Slight overhead:** Rebuilding messages each iteration (negligible - list construction is fast)

### Neutral

- Return type changes from `List[ToolResult]` to `List[ReActIteration]` (same information, different structure)
- Tests need updating but coverage remains the same

---

## Alternatives Considered

### Option A: Tactical Fix (Add AIMessage Only)

Add AIMessage to the message chain without changing the interface:

```python
# After getting tool_calls, before executing:
ai_message = AIMessage(content="", tool_calls=tool_calls)
working_messages.append(ai_message)
```

**Pros:** Quick fix, minimal change
**Cons:** Perpetuates LangChain types in specialist internals, doesn't address architectural concern

### Option B: This ADR (Trace-Based Serialization)

**Pros:** Clean architecture, fixes root cause, aligns with design intent
**Cons:** Larger change, breaking interface

**Decision:** Option B is preferred because it addresses the architectural violation, not just the symptom.

---

## Verification

### Test: File Sorting

```bash
# Test files already exist:
# workspace/sort_by_contents/fruit.txt → "apple"
# workspace/sort_by_contents/animal.txt → "zebra"
# workspace/sort_by_contents/yellow.txt → "banana"

# Prompt:
"For each file in folder sort_by_contents, read the file contents
and move the file into the appropriate existing subfolder based on
the file's contents."

# Expected:
# 1. ProjectDirector reads fruit.txt → sees "apple"
# 2. ProjectDirector calls move_file(fruit.txt, a-m/)
# 3. Repeat for animal.txt, yellow.txt
# 4. Files end up in correct subfolders
```

### Test: Unit Tests Pass

```bash
docker exec langgraph-app pytest app/tests/unit/test_react_mixin.py -v
docker exec langgraph-app pytest app/tests/unit/test_project_director.py -v
```

### Test: Archive Shows Complete Trace

```bash
unzip -p ./logs/archive/run_*.zip llm_traces.jsonl | jq -s '.[].tool_calls'
# Should show both read_file AND move_file calls
```

---

## References

- Issue #88: PROJECT_DIRECTOR loops on reads without moves
- `app/src/specialists/mixins/react_mixin.py` - Current ReAct implementation
- `app/src/specialists/project_director.py` - Main caller
- `app/src/llm/adapters_helpers.py:59-103` - `format_openai_messages()` already handles AIMessage with tool_calls
- Aug/Sep 2025 architectural discussions on pushing HumanMessage/AIMessage out of graph-level code
