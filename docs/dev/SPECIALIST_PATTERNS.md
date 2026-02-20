# Advanced Specialist Patterns

This document covers advanced patterns for specialist development. For the basics of creating a specialist, see [CREATING_A_SPECIALIST.md](CREATING_A_SPECIALIST.md).

**Contents:**
- [Internal Iteration with MCP](#internal-iteration-with-mcp) - Processing collections atomically
- [Procedural Specialists](#procedural-specialists) - Deterministic execution without LLM
- [react_step MCP](#react_step-mcp-for-iterative-tool-use) - LLM-driven iterative tool loops via prompt-prix
- [External MCP Integration](#external-mcp-integration-pattern) - Connecting to Docker containers

---

## Internal Iteration with MCP

When you need to process **collections of items** (files, records, tasks) without creating complex graph-level loops, use the **Internal Iteration** pattern. This pattern processes entire collections atomically within a single specialist execution.

### Problem: Processing Collections

Consider this requirement: "Sort these files into folders: e.txt, l.txt, n.txt, q.txt"

**Naive approach (graph-level looping):**
```
Router -> FileProcessor (e.txt) -> Router -> FileProcessor (l.txt) -> Router -> ...
# 8 routing cycles, expensive LLM calls, complex state tracking
```

**Better approach (internal iteration):**
```
Router -> BatchProcessor (processes all 4 files internally) -> Router
# 2 routing cycles, single atomic operation, simple state
```

### Solution: BatchProcessorSpecialist Example

```python
# app/src/specialists/batch_processor_specialist.py

from typing import Dict, Any, List
from pathlib import Path
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas._batch_ops import BatchSortRequest, BatchSortPlan

class BatchProcessorSpecialist(BaseSpecialist):
    """
    Processes collections with emergent LLM-driven logic.

    Architecture:
    - Graph sees single atomic node
    - Internally iterates over collection
    - Calls MCP services for each item
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Phase 1: Parse user's batch request (LLM tool calling)
        batch_request = self._parse_batch_request(state["messages"])
        # Result: ["e.txt", "l.txt", "n.txt"] + ["a-m/", "n-z/"]

        # Phase 2: LLM generates sorting plan (emergent decision making)
        sort_plan = self._generate_sort_plan(batch_request)
        # Result: [
        #   {file: "e.txt", dest: "a-m/", rationale: "starts with e"},
        #   {file: "l.txt", dest: "a-m/", rationale: "starts with l"},
        #   ...
        # ]

        # Phase 3: Execute operations via MCP (INTERNAL ITERATION)
        results = {"successful": [], "failed": []}

        for decision in sort_plan.decisions:  # <- Internal loop
            try:
                # Check file exists via MCP
                exists = self.mcp_client.call(
                    "file_specialist", "file_exists",
                    path=decision.file_path
                )

                if not exists:
                    results["failed"].append({
                        "file": decision.file_path,
                        "error": "File not found"
                    })
                    continue  # Continue to next file on error

                # Create destination directory
                self.mcp_client.call(
                    "file_specialist", "create_directory",
                    path=decision.destination
                )

                # Move file
                new_path = f"{decision.destination}/{Path(decision.file_path).name}"
                self.mcp_client.call(
                    "file_specialist", "rename_file",
                    old_path=decision.file_path,
                    new_path=new_path
                )

                results["successful"].append({
                    "file": decision.file_path,
                    "destination": new_path,
                    "rationale": decision.rationale
                })

            except Exception as e:
                results["failed"].append({
                    "file": decision.file_path,
                    "error": str(e)
                })

        # Phase 4: Return comprehensive results
        return {
            "artifacts": {
                "batch_sort_summary": {
                    "total": len(sort_plan.decisions),
                    "successful": len(results["successful"]),
                    "failed": len(results["failed"])
                },
                "batch_sort_details": results["successful"] + results["failed"],
                "batch_sort_report.md": self._generate_report(results)
            },
            "messages": [AIMessage(content=self._format_summary(results))]
            # NOTE: Do NOT set task_is_complete. Exit Interview decides completion (ADR-CORE-036).
        }
```

### Key Benefits

1. **Atomic Execution** - All items processed in single graph node
2. **Emergent Logic** - LLM decides actions per item (not hardcoded)
3. **Granular Error Handling** - Tracks success/failure per item
4. **No Graph Looping** - Avoids `recommended_next_specialist` complexity
5. **Rich Observability** - Detailed artifacts with decision rationale

### When to Use This Pattern

**Use Internal Iteration When:**
- Processing collections (files, records, API calls)
- Need emergent per-item decision making (LLM-driven)
- Want atomic operations (all-or-partial success tracking)
- Avoiding routing overhead and state complexity

**Don't Use When:**
- Single item operations (use standard specialist)
- Need graph-level visibility per item (use subgraph)
- Items require different specialist types (use routing)

### Testing Internal Iteration

```python
def test_batch_processor_partial_failure(batch_processor):
    """Test that specialist handles partial failures gracefully."""
    # Mock LLM to return plan with 3 files
    batch_processor.llm_adapter.invoke.side_effect = [...]

    # Mock MCP: first file exists, second doesn't, third exists
    batch_processor.mcp_client.call.side_effect = [
        True,   # file_exists file1
        False,  # file_exists file2 - FAILS HERE
        True,   # file_exists file3
        None,   # create_directory
        "Success"  # rename file1
        None,   # create_directory
        "Success"  # rename file3
    ]

    result = batch_processor.execute(state)

    # Verify partial success
    assert result["artifacts"]["batch_sort_summary"]["successful"] == 2
    assert result["artifacts"]["batch_sort_summary"]["failed"] == 1
    assert "file2" in str(result["artifacts"]["batch_sort_details"])
```

See [app/src/specialists/batch_processor_specialist.py](../../app/src/specialists/batch_processor_specialist.py) for the complete implementation.

---

## Procedural Specialists

A "procedural" specialist executes deterministic code, rather than making a conversational request to an LLM. This pattern is ideal for:

1.  **Deterministic Tasks:** Simple, predictable tasks like data formatting or creating a final report. The `ArchiverSpecialist` is a good example.
2.  **Integrating External Tools:** Integrating powerful third-party libraries (like a code interpreter or web browser).

**Working Example:** See [FACILITATOR.md](../specialists/FACILITATOR.md) for a comprehensive example of a procedural specialist that orchestrates context gathering via MCP.

### The "Plan and Execute" Pattern

This is a best-practice pattern for tool integration. Instead of letting an external library control the LLM, we use a two-phase approach:

1.  **Plan:** Our specialist uses its standard, system-provided LLM adapter to analyze the user's request and generate a structured plan. This plan is a Pydantic object defining exactly what code to run. This enforces a "hard contract" for the LLM's output.
2.  **Execute:** The specialist then takes this structured plan and passes it to the external library for execution. The library is used only as a code runner, without its own LLM or conversational abilities.

This decouples planning from execution, making the system more secure, reliable, and easier to debug.

### Example: Integrating `open-interpreter`

#### Step 1: Install the Dependency

First, add `open-interpreter` to your `pyproject.toml` and run the sync script to install it and update your `requirements.txt` file.

```bash
./scripts/sync-reqs.sh
```

#### Step 2: Configure the Specialist in `config.yaml`

Add a new entry to your `config.yaml` file. For a specialist that uses the "Plan and Execute" pattern, the `type` should be `"hybrid"`. This signals to the system that while the specialist executes code procedurally, it still requires an LLM for the planning phase.

```yaml
# config.yaml
specialists:
  # ... other specialists ...

  open_interpreter_specialist:
    type: "hybrid"
    prompt_file: "open_interpreter_prompt.md"
    description: "Executes shell commands and code (Python, etc.) to perform file system operations, data analysis, or web research. This is the primary tool for interacting with the local machine's files and running scripts."
```

#### Step 3: Define the Structured Output Model (The "Plan")

Create a Pydantic model that defines the structure of the plan our LLM will generate. This file should be placed in `app/src/specialists/schemas/`.

```python
# app/src/specialists/schemas/open_interpreter_schemas.py
from pydantic import BaseModel, Field

class CodeExecutionParams(BaseModel):
    """
    The parameters for executing a block of code in a specified language.
    """
    language: str = Field(
        ...,
        description="The programming language of the code to execute (e.g., 'python', 'bash').",
    )
    code: str = Field(
        ...,
        description="The block of code to be executed.",
    )
```

#### Step 4: Create the Specialist Class (The "Executor")

Create the specialist file `app/src/specialists/open_interpreter_specialist.py`. This class will implement both the "Plan" and "Execute" phases.

```python
# app/src/specialists/open_interpreter_specialist.py

import logging
from typing import Dict, Any

# DO NOT IMPORT 'interpreter' HERE AT THE MODULE LEVEL
from langchain_core.messages import HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import CodeExecutionParams

logger = logging.getLogger(__name__)


class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A specialist that uses the open-interpreter library to execute code.
    It follows a robust two-phase process:
    1. Plan: Use its own LLM adapter to generate a structured code block.
    2. Execute: Programmatically run the generated code using the interpreter library.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _plan_code(self, last_human_message: HumanMessage) -> CodeExecutionParams | None:
        """
        Phase 1: Plan the code to execute by using the LLM to generate a
        structured `CodeExecutionParams` object.
        """
        logger.info("Phase 1: Generating code execution plan...")
        planning_prompt = (
            "Based on the following user request, your task is to generate a single, "
            "self-contained code block to be executed by the open-interpreter. "
            "The code should be self-contained and not require user input. "
            "You must respond by calling the 'CodeExecutionParams' tool."
        )

        request = StandardizedLLMRequest(
            messages=[last_human_message, HumanMessage(content=planning_prompt)],
            tools=[CodeExecutionParams]
        )

        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.error("LLM failed to generate a valid code execution plan. Aborting.")
            return None

        try:
            return CodeExecutionParams(**tool_calls[0]['args'])
        except Exception as e:
            logger.error(f"Failed to parse LLM tool call into CodeExecutionParams: {e}", exc_info=True)
            return None

    def _execute_code(self, code_params: CodeExecutionParams) -> str:
        """
        Phase 2: Execute the code from the plan using the interpreter library.
        """
        logger.info(f"Phase 2: Executing code...\n---\n{code_params.code}\n---")
        try:
            from interpreter import interpreter
            interpreter.auto_run = True
            interpreter.llm.context_window = 0 # We don't want the interpreter's internal LLM to have context
        except ImportError:
            logger.error(
                "The 'open-interpreter' package is not installed. "
                "Please add 'open-interpreter' to pyproject.toml and run './scripts/sync-reqs.sh'."
            )
            return "Error: Required package 'open-interpreter' is not installed."

        interpreter.messages = []  # Clear previous messages
        response_chunks = interpreter.chat(
            f"Please execute this {code_params.language} code:\n```{code_params.language}\n{code_params.code}\n```",
            display=False,
            stream=True
        )

        for _ in response_chunks:
            pass

        outputs = [msg.get('content', '') for msg in interpreter.messages if msg.get('role') == 'computer' and msg.get('type') == 'output' and msg.get('content')]
        final_output = "\n".join(outputs) if outputs else "Code executed with no output."
        logger.info(f"Phase 2 Complete. Execution output: {final_output[:500]}...")
        return final_output

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Generates and executes code based on the user's request.
        """
        if not self.llm_adapter:
            raise RuntimeError(
                "OpenInterpreterSpecialist requires an LLM adapter to generate code. "
                "Ensure it is bound to a provider in user_settings.yaml."
            )

        messages = state.get("messages", [])
        # Find the last human message to use as the basis for the plan.
        # This prevents the specialist from re-evaluating its own previous AI messages.
        last_human_message = next((msg for msg in reversed(messages) if isinstance(msg, HumanMessage)), None)

        if not last_human_message:
            logger.error("OpenInterpreterSpecialist could not find a HumanMessage to act on.")
            return {"error": "OpenInterpreterSpecialist requires a user request to function."}

        # Phase 1: Plan
        code_params = self._plan_code(last_human_message)
        if not code_params:
            return {"error": "OpenInterpreterSpecialist's LLM failed to produce a valid code plan."}

        # Phase 2: Execute
        final_output = self._execute_code(code_params)

        # --- Create a Standardized Response ---
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have executed the following {code_params.language} code:\n\n```\n{code_params.code}\n```\n\n**Result:**\n{final_output}",
        )

        return {
            "messages": [ai_message],
            "scratchpad": {"user_response_snippets": [f"Executed code and got the following result:\n\n{final_output}"]}
            # NOTE: Do NOT set task_is_complete. Exit Interview decides completion (ADR-CORE-036).
        }
```

---

## react_step MCP for Iterative Tool Use

The **react_step MCP pattern** enables specialists to perform ReAct-style loops where the LLM iteratively calls tools until it produces a final answer. This is distinct from BatchProcessor (LLM plans once, procedural execution) and graph routing (each tool call is a separate node).

The loop runs internal to a single specialist execution. Any specialist becomes ReAct-capable by defining a tool routing table and looping on `call_react_step()`.

**History:** The former ~1700-line `ReActMixin` / `ReactEnabledSpecialist` / `react_wrapper.py` was replaced by prompt-prix MCP's `react_step()` primitive (Phase 5, #162). -1720 lines net.

### Shared Helper Pattern

`app/src/mcp/react_step.py` provides the building blocks:

```python
from app.src.mcp.react_step import ToolDef, call_react_step, build_tool_schemas, dispatch_external_tool
```

| Helper | Purpose |
|--------|---------|
| `ToolDef` | Tool definition (name, description, parameters schema) |
| `build_tool_schemas()` | Build JSON schemas from ToolDefs for the LLM |
| `call_react_step()` | Call prompt-prix MCP `react_step` tool |
| `dispatch_external_tool()` | Execute a tool call against the appropriate MCP service |

### Basic Usage

```python
class MyAgenticSpecialist(BaseSpecialist):
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Define tool routing table
        tool_routing = {
            "list_directory": ("filesystem", "list_directory"),
            "read_file": ("filesystem", "read_file"),
            "run_command": ("terminal", "run_command"),
        }

        # 2. Build tool schemas for the LLM
        tool_schemas = build_tool_schemas(tool_routing, self.external_mcp_client)

        # 3. Loop: call react_step, dispatch tools, feed observations back
        trace = []
        for iteration in range(max_iterations):
            result = call_react_step(
                mcp_client=self.external_mcp_client,
                prompt=task_prompt,
                tool_schemas=tool_schemas,
                trace=trace,
            )

            if result.get("completed"):
                return {
                    "artifacts": {"final_response": result["final_response"]},
                    "scratchpad": {"task_is_complete": True},
                }

            # Dispatch pending tool calls
            for tool_call in result.get("pending_tool_calls", []):
                observation = dispatch_external_tool(
                    self.external_mcp_client, tool_call, tool_routing
                )
                trace.append({"tool_call": tool_call, "observation": observation})
```

### How It Works

1. **Build tool schemas** from the specialist's tool routing table
2. **Call `react_step`** on prompt-prix MCP with the task prompt and accumulated trace
3. **prompt-prix makes the LLM call** — returns either `completed=True` with a final response, or `pending_tool_calls`
4. **Specialist dispatches tool calls** to the appropriate MCP services (filesystem, terminal, etc.)
5. **Append observations** to trace and loop back to step 2

### Current Consumers

| Specialist | Tools | Purpose |
|-----------|-------|---------|
| `ProjectDirector` | filesystem, terminal, fork | Filesystem operations, research, subtask delegation |
| `TextAnalysisSpecialist` | semantic-chunker, it-tools, filesystem | Semantic analysis, data processing |
| `ExitInterviewSpecialist` | filesystem | Completion verification with tool access |

### Stagnation Detection

PD's `_check_stagnation()` detects when the LLM repeats the same tool call pattern `CYCLE_MIN_REPETITIONS` times (default: 3). This catches both identical calls and cyclic patterns.

### Termination Protocol

**Critical:** When using JSON schema with logit masking (LM Studio grammar enforcement), the prompt's termination instructions MUST reference the `DONE` action variant — never "respond without tools" or "return plain text." The grammar physically forces an action on every response; the model must use `DONE` to exit the loop.

See CONFIGURATION_GUIDE.md § 6.0 for max_iterations and stagnation configuration.

---

## External MCP Integration Pattern

Specialists that use **external MCP containers** (like NavigatorSpecialist) face a timing challenge: `external_mcp_client` is injected AFTER specialist loading, so it's `None` during pre-flight checks.

### The Two-Stage Validation Pattern

```python
class NavigatorSpecialist(BaseSpecialist):
    SERVICE_NAME = "navigator"

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.external_mcp_client = None  # Injected by GraphBuilder LATER

    def _perform_pre_flight_checks(self) -> bool:
        """
        Stage 1 (Load time): Allow loading even without client
        Stage 2 (Runtime): Verify service connection
        """
        # Load time: client not injected yet - allow loading
        if not self.external_mcp_client:
            return True

        # Runtime: verify actual connection
        if not self.external_mcp_client.is_connected(self.SERVICE_NAME):
            logger.warning(f"{self.specialist_name}: {self.SERVICE_NAME} not connected")
            return False
        return True

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Runtime check: client must now be injected
        if not self.external_mcp_client:
            return self._handle_unavailable(state)

        # Runtime check: service must be connected
        if not self._perform_pre_flight_checks():
            return self._handle_unavailable(state)

        # ... proceed with operation ...
```

### Graceful Degradation

Always provide a fallback when external services are unavailable:

```python
def _handle_unavailable(self, state: Dict[str, Any]) -> Dict[str, Any]:
    """Return helpful message when service unavailable."""
    return {
        "messages": [AIMessage(
            content="The Navigator service is currently unavailable. "
                    "For simple file operations, use File Operations instead.\n\n"
                    "Navigator is needed for:\n"
                    "- Recursive directory deletion\n"
                    "- Glob pattern file search"
        )]
    }
```

### Configuration

External MCP specialists need config in `config.yaml`:

```yaml
specialists:
  navigator_specialist:
    type: "hybrid"
    description: "Complex filesystem operations (recursive delete, glob search)"
    # ADR-CORE-051: Tool permissions
    tools:
      navigator:
        - session_create
        - session_destroy
        - goto
        - click
```

And the service in MCP config:

```yaml
mcp:
  external_mcp:
    enabled: true
    services:
      navigator:
        command: ["docker", "compose", "run", "--rm", "-i", "navigator"]
        enabled: true
```

**See:** [MCP_GUIDE.md](../MCP_GUIDE.md) for MCP integration details.
