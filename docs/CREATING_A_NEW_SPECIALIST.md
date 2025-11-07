# How to Create a New Specialist

This guide provides a detailed, step-by-step walkthrough for creating a new "Specialist" agent within the framework. It is intended for entry-level Python developers who are new to the system.

## Introduction: What is a Specialist?

A Specialist is a modular, reusable component responsible for a single, well-defined task. Think of it as a worker with a specific skill. For example, we have a `FileSpecialist` that knows how to read and write files, and a `WebBuilderSpecialist` that can generate HTML.

By creating new Specialists, you can extend the capabilities of the system to perform new tasks.

## Creating a Standard Specialist

### The Files You Will Touch

Creating a new specialist involves creating and modifying the following files:

1.  `app/src/specialists/your_specialist_name.py`: A new Python file for your specialist's logic.
2.  `app/prompts/your_specialist_prompt.md`: A new prompt file that tells your specialist what to do.
3.  `config.yaml`: The main configuration file where you will register your new specialist.
4.  `app/tests/unit/test_your_specialist_name.py`: A new unit test file to verify your specialist's behavior.

### Step 1: Create the Specialist Python File

First, you need to create a new Python file for your specialist in the `app/src/specialists/` directory. The filename should be the `snake_case` version of your specialist's class name. For example, if your specialist is named `CodeWriterSpecialist`, the filename should be `code_writer_specialist.py`.

Here is a template for a new specialist file:

```python
# app/src/specialists/code_writer_specialist.py

# Import the necessary base class and data structures
from typing import Dict, Any
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, HumanMessage

# Define your new specialist class. It must inherit from BaseSpecialist.
class CodeWriterSpecialist(BaseSpecialist):
    """A specialist that writes Python code based on a user's request."""

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """Initializes the specialist.

        The most important part of this method is calling the parent class's
        __init__ method with the specialist's name and its configuration dictionary.
        """
        # The specialist_name and specialist_config are passed in by the GraphBuilder.
        # The name must match the key in config.yaml.
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> dict:
        """This is the main method where your specialist's core logic goes.

        The `execute` method in the `BaseSpecialist` class handles all the
        common boilerplate like logging and error handling. You only need to
        implement the logic specific to this specialist.
        """
        # The specialist's configuration was injected by the GraphBuilder via the
        # constructor and is available as `self.specialist_config`.

        # Get the full message history from the state.
        messages = state["messages"]

        # 1. Create a standardized request to the Language Model.
        #    This object bundles up the messages for the LLM.
        #    Passing the full history gives the LLM context.
        request = StandardizedLLMRequest(
            messages=messages
        )

        # 2. Invoke the LLM adapter.
        #    The self.llm_adapter is automatically configured for this specialist
        #    based on the settings in config.yaml.
        response_data = self.llm_adapter.invoke(request)

        # 3. Process the response from the LLM.
        #    In this case, we are just taking the text response and adding it
        #    to the message history as an AI message.
        ai_response_content = response_data.get(
            "text_response", "I am unable to provide a response at this time."
        )

        # Use the helper to create a standardized message with the LLM name included.
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=ai_response_content,
        )

        # 4. Return the updated state.
        #    Only return the *new* messages you want to add to the history. The
        #    graph will automatically append them.
        return {"messages": [ai_message]}
```

### Specialist Best Practices

To ensure your specialist integrates smoothly and reliably into the system, please follow these best practices:

*   **Return Only Deltas:** Your specialist should only return the *new* state changes (the "delta"). For example, only return the new `AIMessage` you created, not the entire message history. The graph is configured to append new messages automatically.
*   **Use Standard State Management Patterns:** To ensure your specialist is compatible with the system architecture, use the following state management patterns:
    *   **For significant data outputs:** Write to the `artifacts` dictionary.
        *   `return {"artifacts": {"my_report.txt": "This is the content..."}}`
    *   **For private, transient state (e.g., counters):** Write to the `scratchpad` dictionary.
        *   `return {"scratchpad": {"my_specialist_counter": 1}}`
    *   **For standard specialists:** Return messages to append to conversation history.
        *   `return {"messages": [ai_message]}`
    *   **CRITICAL - For parallel execution specialists:** Do NOT return messages key.
        *   See "Special Case: Parallel Execution Specialists" section below for details.
*   **Do Not Modify Global State Counters:** The `turn_count` is managed exclusively by the `RouterSpecialist`. Do not attempt to change this value from within your specialist, as it will break the workflow in unpredictable ways.
*   **Use Agentic Robustness Patterns:** Leverage the built-in patterns for self-correction (`recommended_specialists`) and task completion (`task_is_complete: True`) to create more intelligent and resilient workflows. See the `DEVELOPERS_GUIDE.md` for more details.

### Special Case: Parallel Execution Specialists

When creating specialists that will be executed **in parallel** as part of a fan-out/join pattern (like the progenitors in CORE-CHAT-002), you MUST follow a different state management pattern:

**CRITICAL STATE MANAGEMENT FOR PARALLEL NODES:**

Parallel specialists (nodes before a join node) must write ONLY to `artifacts`, never to `messages`:

```python
def _execute_logic(self, state: dict) -> dict:
    """Execute parallel node logic."""
    # ... generate response ...

    # WRONG - DO NOT DO THIS in parallel nodes:
    # return {"messages": [ai_message]}

    # CORRECT - Write to artifacts only:
    return {
        "artifacts": {
            "my_response": ai_response_content
        }
    }
```

**Why This Matters:**

In LangGraph's fan-out/join pattern:
- **Parallel nodes (fan-out):** Write to temporary storage (`artifacts`)
- **Join node:** Reads artifacts and writes to permanent storage (`messages`)

This prevents message pollution and enables proper multi-turn conversation cross-referencing.

**Example - Tiered Chat Progenitors:**

```python
# ProgenitorAlphaSpecialist - PARALLEL NODE
def _execute_logic(self, state: dict) -> dict:
    # ... LLM call ...
    return {
        "artifacts": {"alpha_response": response_content}
        # NO "messages" key!
    }

# TieredSynthesizerSpecialist - JOIN NODE
def _execute_logic(self, state: dict) -> dict:
    alpha = state["artifacts"]["alpha_response"]
    bravo = state["artifacts"]["bravo_response"]
    combined = format_both(alpha, bravo)

    # Join node DOES write to messages
    return {
        "messages": [create_llm_message(self.specialist_name, self.llm_adapter, combined)]
    }
```

**References:**
- See `app/src/specialists/progenitor_alpha_specialist.py` for a working example
- See DEVELOPERS_GUIDE.md Section 4.7 for the Virtual Coordinator pattern

### Optional: Exposing Specialist Functions via MCP

**When to Use MCP:** If your specialist provides **deterministic utility functions** that other specialists might need to call synchronously (e.g., file operations, date/time functions, validation logic), you should expose those functions via MCP (Message-Centric Protocol).

**When NOT to Use MCP:** If your specialist performs LLM-driven reasoning or complex workflows, it should remain graph-routed and not expose MCP services.

#### MCP Service Registration Pattern

To expose your specialist's functions as MCP services, implement the `register_mcp_services()` method:

```python
# app/src/specialists/datetime_specialist.py

from typing import Dict, Any
from datetime import datetime
from .base import BaseSpecialist

class DateTimeSpecialist(BaseSpecialist):
    """A specialist that provides date/time utility functions via MCP."""

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

    def register_mcp_services(self, registry: 'McpRegistry'):
        """Register utility functions as MCP services."""
        registry.register_service(self.specialist_name, {
            "get_current_date": self.get_current_date,
            "get_current_time": self.get_current_time,
            "format_timestamp": self.format_timestamp,
        })

    # MCP service functions - simple, deterministic methods
    def get_current_date(self) -> str:
        """Returns current date in YYYY-MM-DD format."""
        return datetime.now().strftime("%Y-%m-%d")

    def get_current_time(self) -> str:
        """Returns current time in HH:MM:SS format."""
        return datetime.now().strftime("%H:%M:%S")

    def format_timestamp(self, timestamp: int, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Formats a Unix timestamp using the specified format string."""
        return datetime.fromtimestamp(timestamp).strftime(format_str)

    def _execute_logic(self, state: dict) -> dict:
        """Optional: Can still participate in graph routing if needed."""
        # This specialist could operate in "MCP-only" mode by making this a no-op
        return {}
```

#### Using MCP Services from Other Specialists

Once registered, other specialists can call your MCP services synchronously:

```python
# app/src/specialists/report_generator_specialist.py

class ReportGeneratorSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # Synchronous call to DateTimeSpecialist via MCP
        current_date = self.mcp_client.call("datetime_specialist", "get_current_date")

        report = f"# Report Generated on {current_date}\n\n"
        # ... rest of report generation ...

        return {"artifacts": {"report.md": report}}
```

#### MCP-Only Pattern (Advanced)

For specialists that ONLY provide utility services and never participate in graph routing (like `FileSpecialist`), you can make `_execute_logic()` a complete no-op:

```python
class UtilitySpecialist(BaseSpecialist):
    def register_mcp_services(self, registry: 'McpRegistry'):
        """Register all utility functions."""
        registry.register_service(self.specialist_name, {
            "utility_func_1": self.utility_func_1,
            "utility_func_2": self.utility_func_2,
        })

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """No-op for MCP-only mode."""
        logger.warning(f"{self.specialist_name} operates exclusively via MCP")
        return {}

    def utility_func_1(self, param: str) -> str:
        """MCP service function."""
        return f"Processed: {param}"

    def utility_func_2(self, x: int, y: int) -> int:
        """MCP service function."""
        return x + y
```

#### MCP Best Practices

1. **Keep service functions simple** - No LLM calls, no complex state management
2. **Return serializable data** - Dicts, lists, strings, numbers, bools (no custom objects)
3. **Handle errors gracefully** - Raise clear exceptions with descriptive messages
4. **Document parameters** - Use type hints and docstrings for all service functions
5. **Security considerations** - Validate inputs, especially for file paths or external data

#### Error Handling in MCP Calls

MCP provides two invocation patterns:

```python
# Raises ValueError on error (use for critical operations)
result = self.mcp_client.call("service", "function", param="value")

# Returns (success, result) tuple (use for fault-tolerant workflows)
success, result = self.mcp_client.call_safe("service", "function", param="value")
if success:
    # result contains the return value
else:
    # result contains the error message string
```

#### Reference Implementation

See `app/src/specialists/file_specialist.py` for a complete MCP-only specialist implementation with:
- 6 MCP service functions (file_exists, read_file, write_file, list_files, create_directory, create_zip)
- Path validation security (prevents directory traversal)
- Comprehensive test coverage (39 tests)

**Additional Documentation:**
- See DEVELOPERS_GUIDE.md Section 4.5 for MCP vs Dossier usage guidelines
- See ADR-CORE-008_MCP-Architecture.md for complete architectural details

### Step 2: Create the Prompt File

Next, create a new prompt file in the `app/prompts/` directory. This file contains the instructions that will be sent to the Language Model. The filename should be descriptive and match the `prompt_file` key you will set in `config.yaml`.

For our `CodeWriterSpecialist`, we can create a file named `code_writer_prompt.md`:

```markdown
# app/prompts/code_writer_prompt.md

You are a world-class Python programmer. Your task is to write clean, efficient, and well-documented Python code based on a user's request.

Only output the code itself. Do not add any explanations or pleasantries.
```

### Step 3: Configure the Specialist in `config.yaml`

Now, you need to register your new specialist in the `config.yaml` file in the root directory. This tells the system about your specialist and how to configure it.

Add a new entry under the `specialists` key:

*   The key (`code_writer_specialist`) must match the `specialist_name` you set in your specialist's `__init__` method.
*   `type`: Set to `"llm"` for a standard specialist.
*   `prompt_file`: The name of the prompt file you created.
*   `description`: A clear, concise description of the specialist's capabilities. This is **critical** for the `RouterSpecialist` and `PromptTriageSpecialist` to make accurate routing decisions.

```yaml
# config.yaml

specialists:
  # ... other specialists ...

  code_writer_specialist:
    type: "llm"
    prompt_file: "code_writer_prompt.md"
    description: "A specialist that writes clean, efficient Python code based on a user's request."
```

After registering the specialist in the system blueprint (`config.yaml`), you can optionally bind it to a specific LLM configuration in your local `user_settings.yaml` file. If you don't, it will use the `default_llm_config`.

### Step 4: Testing Your New Specialist

After creating your specialist, it's important to test it. You can write a simple unit test in the `app/tests/unit/` directory.

The project uses `pytest` as its testing framework. Here is an example test for our `CodeWriterSpecialist` that follows the `pytest` style.

```python# app/tests/unit/test_code_writer_specialist.py

import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage

@pytest.fixture
def code_writer_specialist(initialized_specialist_factory):
    """Fixture to provide an initialized CodeWriterSpecialist."""
    return initialized_specialist_factory("CodeWriterSpecialist")

def test_code_writer_specialist_execute(code_writer_specialist):
    # Arrange
    # Mock the LLM adapter to avoid making a real API call.
    # The adapter is already mocked by the initialized_specialist_factory.
    mock_response = "print('Hello, World!')"
    code_writer_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Define the initial state with a user message.
    initial_state = {"messages": [HumanMessage(content="Write a hello world script.")]}

    # Act
    # We test the internal `_execute_logic` method directly.
    result_state = code_writer_specialist._execute_logic(initial_state)

    # Assert
    # Check that the LLM adapter was called once.
    code_writer_specialist.llm_adapter.invoke.assert_called_once_with(ANY)

    # Check that the new AI message was added to the state correctly.
    # The specialist should only return the *new* message it created.
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response
```

To run the tests, simply run `pytest` from the root directory.

## Advanced: Creating a Procedural Specialist

A "procedural" specialist is one that executes deterministic code, rather than making a conversational request to an LLM. This pattern is ideal for two scenarios:

1.  **Deterministic Tasks:** For simple, predictable tasks like data formatting or creating a final report, a procedural specialist is more efficient and reliable. The `ArchiverSpecialist` is a good example.
2.  **Integrating External Tools:** For integrating powerful, third-party libraries (like a code interpreter or web browser), a procedural specialist acts as a safe, clean integration point.

This guide focuses on the second, more advanced use case, demonstrating the **"Plan and Execute"** pattern for safely integrating the `open-interpreter` library.

### The "Plan and Execute" Pattern

This is a best-practice pattern for tool integration. Instead of letting an external library control the LLM, we use a two-phase approach:

1.  **Plan:** Our specialist uses its standard, system-provided LLM adapter to analyze the user's request and generate a structured plan. This plan is a Pydantic object defining exactly what code to run. This enforces a "hard contract" for the LLM's output.
2.  **Execute:** The specialist then takes this structured plan and passes it to the external library for execution. The library is used only as a code runner, without its own LLM or conversational abilities.

This decouples planning from execution, making the system more secure, reliable, and easier to debug.

### Example: Integrating `open-interpreter`

Let's walk through the modern way to integrate `open-interpreter` using the "Plan and Execute" pattern.

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
            # Add a user-facing summary of the action to the scratchpad.
            "scratchpad": {"user_response_snippets": [f"Executed code and got the following result:\n\n{final_output}"]},
            "task_is_complete": True # Signal that the task is done to prevent looping.
        }
```

## Conclusion

That's it! You have successfully created a new specialist agent. The `GraphBuilder` class will automatically discover and integrate your new specialist at build time. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
