Of course. I have updated the two primary documentation files based on our comprehensive audit.

In revising these documents, I have not only corrected the identified discrepancies but also refined the language and structure to improve clarity and better convey the system's architectural principles. The most significant change is the complete rewrite of the "Procedural Specialist" example in the tutorial to demonstrate the superior "Plan and Execute" pattern now used in the codebase.

Below are the complete, updated listings for each document, ready for inclusion in your project.

---

Here is the updated `How to Create a New Specialist` guide:

```markdown
# How to Create a New Specialist

This guide provides a detailed, step-by-step walkthrough for creating a new "Specialist" agent within the SpecialistHub framework. It is intended for entry-level Python developers who are new to the system.

## Introduction: What is a Specialist?

A Specialist is a modular, reusable component responsible for a single, well-defined task. Think of it as a worker with a specific skill. For example, we have a `FileSpecialist` that knows how to read and write files, and a `WebBuilderSpecialist` that can generate HTML.

By creating new Specialists, you can extend the capabilities of the system to perform new tasks.

## Creating a Standard Specialist

### The Files You Will Touch

Creating a new specialist involves creating and modifying a few files:

1.  `app/src/specialists/your_specialist_name.py`: A new Python file for your specialist's logic.
2.  `app/prompts/your_specialist_prompt.md`: A new prompt file that tells your specialist what to do.
3.  `config.yaml`: The main configuration file where you will register your new specialist.

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
        # The specialist_name and specialist_config are passed in by the ChiefOfStaff.
        # The name must match the key in config.yaml.
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> dict:
        """This is the main method where your specialist's core logic goes.

        The `execute` method in the `BaseSpecialist` class handles all the
        common boilerplate like logging and error handling. You only need to
        implement the logic specific to this specialist.
        """
        # The specialist's configuration was injected by the ChiefOfStaff via the
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
        #    Only return the *new* messages you want to add to the history.
        return {"messages": [ai_message]}
```

### Specialist Best Practices

To ensure your specialist integrates smoothly and reliably into the system, please follow these best practices:

*   **Return Only Deltas:** Your specialist should only return the *new* state changes (the "delta"). For example, only return the new `AIMessage` you created, not the entire message history. The graph is configured to append new messages automatically.
*   **Do Not Modify Global State Counters:** The `turn_count` is managed exclusively by the `RouterSpecialist`. Do not attempt to change this value from within your specialist, as it will break the workflow in unpredictable ways.
*   **Use Agentic Robustness Patterns:** Leverage the built-in patterns for self-correction (`recommended_specialists`) and task completion (`task_is_complete: True`) to create more intelligent and resilient workflows. See the `DEVELOPERS_GUIDE.md` for more details.

### Step 2: Create the Prompt File

Next, create a new prompt file in the `app/prompts/` directory. This file contains the instructions that will be sent to the Language Model. The filename should be descriptive and match the `prompt_file` key you will set in `config.yaml`.

For our `CodeWriterSpecialist`, we can create a file named `code_writer_prompt.md`:

```markdown
# app/prompts/code_writer_prompt.md

You are a world-class Python programmer. Your task is to write clean, efficient, and well-documented Python code based on the user's request.

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

# ... other sections like llm_providers ...

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

```python
# app/tests/unit/test_code_writer_specialist.py

from unittest.mock import MagicMock, ANY
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.code_writer_specialist import CodeWriterSpecialist

def test_code_writer_specialist_execute():
    # Arrange
    specialist_config: Dict[str, Any] = {}
    specialist = CodeWriterSpecialist(
        specialist_name="code_writer_specialist",
        specialist_config=specialist_config
    )
    
    # Mock the LLM adapter to avoid making a real API call.
    specialist.llm_adapter = MagicMock()
    mock_response = "print('Hello, World!')"
    specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Define the initial state with a user message.
    initial_state = {
        "messages": [HumanMessage(content="Write a hello world script.")]
    }

    # Act
    # We test the internal `_execute_logic` method directly.
    result_state = specialist._execute_logic(initial_state)

    # Assert
    # Check that the LLM adapter was called once.
    specialist.llm_adapter.invoke.assert_called_once_with(ANY)

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

Add a new entry to your `config.yaml` file. Note that `type` is `"procedural"`, as it executes code directly.

```yaml
# config.yaml
specialists:
  # ... other specialists ...

  open_interpreter_specialist:
    type: "procedural"
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

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .base import BaseSpecialist
from .schemas.open_interpreter_schemas import CodeExecutionParams
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A procedural specialist that uses the open-interpreter library
    following a 'Plan and Execute' pattern.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Lazily import the interpreter to keep startup times fast.
        self._interpreter = None
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    @property
    def interpreter(self):
        """Lazy loader for the interpreter singleton."""
        if self._interpreter is None:
            from interpreter import interpreter
            interpreter.auto_run = True
            interpreter.llm.model = "" # We disable the internal LLM
            interpreter.llm.api_key = "no_key_needed"
            self._interpreter = interpreter
        return self._interpreter

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise RuntimeError("OpenInterpreterSpecialist requires an LLM adapter for planning.")

        messages = state.get("messages", [])

        # === 1. PLAN PHASE ===
        # Use the system LLM to generate a structured plan for code execution.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[CodeExecutionParams],
            tool_choice="CodeExecutionParams"
        )
        response = self.llm_adapter.invoke(request)
        
        # Check if the LLM returned a valid tool call
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            # Fallback if the LLM fails to generate a plan
            return {"messages": [AIMessage(content="I was unable to determine which code to execute.", name=self.specialist_name)]}

        # === 2. EXECUTE PHASE ===
        # Execute the plan using the open-interpreter library as a code runner.
        params = tool_calls[0]['args']
        language = params.get("language")
        code_to_run = params.get("code")

        if not all([language, code_to_run]):
            return {"messages": [AIMessage(content="Invalid code execution plan received.", name=self.specialist_name)]}

        # Reset interpreter state and execute
        self.interpreter.messages = []
        execution_messages = self.interpreter.chat(
            f"Please execute this {language} code:\n```{language}\n{code_to_run}\n```",
            display=False,
            stream=False,
        )

        # Parse the output to find the result of the code execution.
        computer_outputs = [m['content'] for m in execution_messages if m.get('role') == 'computer']
        final_output = "\n".join(computer_outputs) if computer_outputs else "Task completed with no output."

        # Return the result as a ToolMessage to provide clear context to the graph.
        tool_message = ToolMessage(
            content=final_output,
            tool_call_id=tool_calls[0]['id'],
            name=self.specialist_name
        )
        
        # Signal that the task is complete to trigger the archiver.
        return {"messages": [tool_message], "task_is_complete": True}
```

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
```

---

Here is the updated `System Architecture & Developer's Guide`:

```markdown
# System Architecture & Developer's Guide
# Version: 2.5
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system. It is designed to be parsed by both human developers and autonomous AI agents.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

**Open Core Model:** This project is the "core" in an open core model. It provides generic, foundational capabilities under a permissive MIT license. Specialized, proprietary features (e.g., specific product integrations, complex UIs, opinionated agent personas) are intended to be built in separate, private projects that use this scaffold as a dependency or starting point.

**Core Philosophy:** The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code).
2.  **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph. It uses its LLM to analyze the conversation state and decides which Specialist should run next, updating the `GraphState` with its choice.
3.  **Structural Orchestrator (`ChiefOfStaff`):** A high-level system component responsible for building the `LangGraph` instance, loading all Specialists from the configuration, and enforcing global rules (like detecting unproductive loops or handling errors). It reads the decision made by the `RouterSpecialist` to direct the flow of the graph.

## 2.0 Getting Started

Follow these steps to set up and run the project.

### 2.1 Prerequisites
*   Python 3.10+
*   Git

### 2.2 Installation

To set up your development environment, run the appropriate installation script for your operating system from the project root:

*   On **Linux/macOS**:
    `./scripts/install.sh`
*   On **Windows**:
    `.\scripts\install.bat`

These scripts will create a virtual environment, install dependencies, and copy example configuration files. After running the script, remember to edit `.env` with your API keys.

### 2.3 Configuration

The system uses a three-layer configuration model to cleanly separate concerns.

1.  **Layer 1: The System Blueprint (`config.yaml`)**: Defines the complete set of capabilities for the application. It lists all possible LLM providers and all available specialists. This file **SHOULD** be committed to Git.
2.  **Layer 2: User Settings (`user_settings.yaml`)**: Allows a user to make choices from the blueprint, primarily by binding specialists to specific LLM configurations. This file **should NOT** be committed to Git.
3.  **Layer 3: Secrets (`.env`)**: Holds secrets like API keys. This file **must NEVER** be committed to Git.

### 2.4 Running the Application

Use the provided scripts in the project root to run the application.

*   On **Linux/macOS**: `./scripts/server.sh start`
*   On **Windows**: `.\scripts\server.bat start`

### 2.5 Running Tests

To ensure the system is functioning correctly, run the full suite of unit tests using `pytest`.

`pytest`

### 2.6 Interacting via CLI

Once the FastAPI server is running, you can interact with it from a separate terminal using the provided `cli` script.

*   On **Linux/macOS**: `./scripts/cli.sh "Your prompt for the agent goes here."`
*   On **Windows**: `.\scripts\cli.bat "Your prompt for the agent goes here."`

## 3.0 System Architecture

### 3.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 3.2 The Adapter Factory Pattern
*   **Role:** Centralized component instantiation.
*   **Implementation:** The `AdapterFactory` reads the merged configuration to create and configure the correct LLM adapter for a given specialist.
*   **Principle:** Specialists request an adapter by name; they do not know the details of its creation. This decouples business logic from infrastructure.

### 3.3 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist` and implement the `_execute_logic` method.
*   **Function:** A Specialist performs a single atomic task, usually by creating a `StandardizedLLMRequest` and passing it to its configured LLM adapter.

**Procedural Specialists:**
The system supports specialists that execute deterministic code. This is ideal for simple tasks (like archiving) or for safely integrating external tools that may have their own internal logic (like `open-interpreter`). For a detailed walkthrough of the best-practice "Plan and Execute" pattern for tool integration, see the `How to Create a New Specialist` guide.

### 3.4 Schema Enforcement Strategy
The system uses a "hard contract" approach to ensure LLMs produce reliable, structured JSON output. This is implemented via a progressive enhancement strategy in the LLM adapters, using the strongest enforcement mechanism available for any given provider (e.g., `response_format` for OpenAI-compatible models, `response_mime_type` for Gemini).

### 3.5 Application Internals: Separation of Concerns
The `app/src` directory is organized to enforce modularity:
*   `specialists/`: The core agentic workforce. Each file defines a `BaseSpecialist` subclass.
*   `workflow/`: High-level orchestration logic, including the `ChiefOfStaff`.
*   `llm/`: Abstractions for interacting with different LLMs (`adapter`, `factory`).
*   `graph/`: Definition of the shared `GraphState`.
*   `utils/`: Shared utilities like the `ConfigLoader`.

### 3.6 Agentic Robustness Patterns

This scaffold implements several advanced patterns to create a more robust, resilient agentic system.

*   **Two-Stage Semantic Routing:**
    *   **Stage 1: Recommendation (`PromptTriageSpecialist`):** This specialist analyzes the user's initial prompt against the descriptions of all available specialists and outputs a `recommended_specialists` list.
    *   **Stage 2: Dispatch (`RouterSpecialist`):** The Router uses this list to make an intelligent decision. If the list contains one specialist, it performs a fast, deterministic handoff. If it contains multiple, it uses the list as a filtered menu for its LLM, improving accuracy and reducing cost.

*   **Self-Correction via Precondition Checks:** The system uses a centralized, declarative approach for self-correction. Instead of each specialist checking its own preconditions, the `ChiefOfStaff` does it automatically. By adding a `requires_artifacts: ["file_content"]` key to a specialist's configuration in `config.yaml`, you declare its dependencies. If this specialist is called before the required artifact exists in the `GraphState`, the `ChiefOfStaff`'s safe executor will intercept the call, generate a standardized error message, and recommend a specialist that can produce the missing artifact (e.g., `file_specialist`). This is more robust and maintainable than per-specialist implementation.

*   **Programmatic Task Completion:** To provide a deterministic signal that a task is finished, specialists that produce a final artifact (e.g., `web_builder`) set a `task_is_complete: True` flag in the state they return. The `RouterSpecialist` checks for this flag and, if present, routes to the `archiver_specialist` for a final report before ending the workflow.

*   **Iterative Refinement:** A specialist can improve its work over multiple steps. This is managed by including a cycle count (e.g., `refinement_cycles: 3`) in the `system_plan`. The `WebBuilder` specialist manages a counter in the `GraphState`. For each cycle, it generates HTML and then uses the `recommended_specialists` pattern to request a `CriticSpecialist` to review its work. This creates a controlled `WebBuilder -> Critic -> WebBuilder` loop. Once the cycles are complete, `WebBuilder` sets `task_is_complete: True`.

*   **Centralized State Integrity:**
    *   **Declarative State Updates:** The `GraphState` itself defines how its fields are updated (e.g., `messages: Annotated[List, operator.add]`), instructing LangGraph to always *append* to the message history, preventing accidental data loss.
    *   **Protective Wrappers:** The `ChiefOfStaff` wraps each specialist's execution in a "safe executor." This wrapper intercepts the specialist's output and sanitizes it before it's merged into the global state, providing centralized enforcement of global rules (like preventing specialists from modifying the `turn_count`).

## 4.0 How to Extend the System

### 4.1 Adding New Specialists

The primary way to extend the system's capabilities is by adding new specialists. For a detailed, step-by-step tutorial on this process, please refer to the **`How to Create a New Specialist`** guide.

### 4.2 Managing Dependencies

This project uses `pyproject.toml` as the single source of truth for dependencies and `pip-tools` to generate pinned `requirements.txt` files.

**To add or update a dependency:**
1.  Edit `pyproject.toml`.
2.  Run the sync script: `./scripts/sync-reqs.sh` (or `.bat` on Windows).
3.  Commit the changes to `pyproject.toml` **and** the generated `requirements.txt` files.

## 5.0 Project Structure Reference

For a comprehensive, file-by-file explanation of the project's structure, please see the **Project Structure Deep Dive** in `PROJECT_STRUCTURE.md`.
```