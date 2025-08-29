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

# app/src/specialists/code_writer_specialist.py

# Import the necessary base class and data structures
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, HumanMessage

# Define your new specialist class. It must inherit from BaseSpecialist.
class CodeWriterSpecialist(BaseSpecialist):
    """A specialist that writes Python code based on a user's request."""

    def __init__(self, specialist_name: str):
        """Initializes the specialist.

        The most important part of this method is calling the parent class's
        __init__ method with the specialist's name.
        """
        # The specialist_name is passed in by the ChiefOfStaff and must match the key in config.yaml.
        super().__init__(specialist_name)

    def _execute_logic(self, state: dict) -> dict:
        """This is the main method where your specialist's core logic goes.

        The `execute` method in the `BaseSpecialist` class handles all the
        common boilerplate like logging and error handling. You only need to
        implement the logic specific to this specialist.
        """
        # The specialist's configuration is injected by the ChiefOfStaff and
        # is available via `self.specialist_config`.
        # For example: my_setting = self.specialist_config.get("my_setting")

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

### Specialist Best Practices

To ensure your specialist integrates smoothly and reliably into the system, please follow these best practices:

*   **Return Only Deltas:** Your specialist should only return the *new* state changes (the "delta"). For example, only return the new `AIMessage` you created, not the entire message history. The graph is configured to append new messages automatically.
*   **Do Not Modify Global State Counters:** The `turn_count` is managed exclusively by the `RouterSpecialist`. Do not attempt to change this value from within your specialist, as it will break the workflow in unpredictable ways.
*   **Use Agentic Robustness Patterns:** Leverage the built-in patterns for self-correction (`recommended_specialists`) and task completion (`task_is_complete: True`) to create more intelligent and resilient workflows. See the `DEVELOPERS_GUIDE.md` for more details.


### Step 2: Create the Prompt File

Next, create a new prompt file in the `app/prompts/` directory. This file contains the instructions that will be sent to the Language Model. The filename should be descriptive and match the `prompt_file` key you will set in `config.yaml`.

For our `CodeWriterSpecialist`, we can create a file named `code_writer_prompt.md`:

# app/prompts/code_writer_prompt.md

You are a world-class Python programmer. Your task is to write clean, efficient, and well-documented Python code based on the user's request.

Only output the code itself. Do not add any explanations or pleasantries.

### Step 3: Configure the Specialist in `config.yaml`

Now, you need to register your new specialist in the `config.yaml` file in the root directory. This tells the system about your specialist and how to configure it.

Add a new entry under the `specialists` key:

*   The key (`code_writer_specialist`) must match the `specialist_name` you set in your specialist's `__init__` method.
*   `type`: Set to `"llm"` for a standard specialist.
*   `prompt_file`: The name of the prompt file you created.
*   `description`: A clear, concise description of the specialist's capabilities. This is **critical** for the `RouterSpecialist` and `PromptTriageSpecialist` to make accurate routing decisions.

# config.yaml

# ... other sections like llm_providers ...

specialists:
  # ... other specialists ...

  code_writer_specialist:
    type: "llm"
    prompt_file: "code_writer_prompt.md"
    description: "A specialist that writes clean, efficient Python code based on a user's request."

After registering the specialist in the system blueprint (`config.yaml`), you can optionally bind it to a specific LLM configuration in your local `user_settings.yaml` file. If you don't, it will use the `default_llm_config`.

### Step 4: Testing Your New Specialist

After creating your specialist, it's important to test it. You can write a simple unit test in the `app/tests/unit/` directory.

The project uses `pytest` as its testing framework. Here is an example test for our `CodeWriterSpecialist` that follows the `pytest` style (which is simpler and more direct than using `unittest.TestCase`).

# app/tests/unit/test_code_writer_specialist.py

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.code_writer_specialist import CodeWriterSpecialist

def test_code_writer_specialist_execute():
    # Arrange
    # The specialist's __init__ requires a name.
    specialist = CodeWriterSpecialist("code_writer_specialist")

    # In tests, you may need to manually set the config if your logic uses it.
    specialist.specialist_config = {}
    
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
    specialist.llm_adapter.invoke.assert_called_once()

    # Check that the new AI message was added to the state correctly.
    # The specialist should only return the *new* message it created.
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response

To run the tests, simply run `pytest` from the root directory.

### Advanced Specialist Patterns

The example above shows a basic specialist. However, the scaffold's architecture supports more advanced patterns for creating robust, intelligent agents. You should leverage these patterns when building your own specialists.

*   **Structured Output:** Instead of returning plain text, you can enforce a specific JSON schema for the LLM's response. This is done by passing an `output_model_class` (a Pydantic model) or a list of `tools` to the `StandardizedLLMRequest`. This dramatically improves reliability.
    *   **Example:** See how `FileSpecialist` uses Pydantic models like `ReadFileParams` and `WriteFileParams` as tools.

*   **Self-Correction and Recommendations:** A specialist can guide the workflow if it's called at the wrong time. If a specialist cannot perform its task because a precondition is not met (e.g., it needs a file to be read first), it should return a `recommended_specialists` list in its state update. The `RouterSpecialist` will use this recommendation to route to the correct specialist next, effectively "self-correcting" the workflow.
    *   **Example:** See `TextAnalysisSpecialist`. If it's called when `text_to_process` is not in the state, it returns `{"recommended_specialists": ["file_specialist"]}`.

*   **Programmatic Task Completion:** Specialists that produce a final, user-facing artifact (like a webpage) should signal that the primary goal is achieved. To do this, they include `task_is_complete: True` in the state they return. The `RouterSpecialist` will see this flag and route the workflow to the `archiver_specialist` for a final report before the graph ends. This provides a clean, deterministic way to finish a task.
    *   **Example:** See `web_builder`. After it successfully generates the HTML, it sets this flag to `True`. This is appropriate because creating the webpage is often the final step of a user's request.

For a deeper understanding of these patterns, refer to the **"Agentic Robustness Patterns"** section in the **Developer's Guide**.

## Advanced: Creating a Procedural Specialist

A "procedural" specialist is one that executes Python code directly, rather than making a request to an LLM through the system's adapter factory. This pattern is ideal for two scenarios:

1.  **Deterministic Tasks:** For simple, predictable tasks like data formatting or creating a final report, a procedural specialist is more efficient and reliable than an LLM. The `ArchiverSpecialist` is a good example.
2.  **Integrating External Libraries:** For integrating powerful, third-party libraries that may have their own internal LLM (like `open-interpreter`), a procedural specialist acts as a clean integration point.

This guide focuses on the second, more advanced use case.

### How it Works

The key is a clean separation of concerns. The specialist class itself contains the integration logic, while the configuration files define how it's wired into the system.

1.  **Install the Library:** The external tool is installed as a standard Python dependency via `pip-tools`.
2.  **Define in `config.yaml`:** You register the specialist in the system blueprint with `type: "procedural"`.
3.  **Bind in `user_settings.yaml` (If Needed):** If the procedural specialist needs an LLM (like `open-interpreter`), you bind it to a provider in your `user_settings.yaml`. This follows the system's 3-tier configuration philosophy, separating developer blueprints from user-level choices.
4.  **Create the Specialist Class:** The specialist inherits from `BaseSpecialist`. The `ChiefOfStaff` will see the binding from the merged configuration and automatically create and inject a configured `llm_adapter` instance.
4.  **Implement the Logic:** The specialist's `_execute_logic` method calls the external library directly.

### Example: Integrating `open-interpreter`

Let's walk through the modern way to integrate `open-interpreter`, which allows an LLM to execute code locally.

#### Step 1: Install the Dependency

First, add `open-interpreter` to your `pyproject.toml` and run the sync script to install it and update your `requirements.txt` file.

```bash
./scripts/sync-reqs.sh
```

#### Step 2: Configure the Specialist in `config.yaml`

Add a new entry to your `config.yaml` file under the `specialists` key.

```yaml
specialists:
  # ... other specialists ...

  open_interpreter_specialist:
    type: "procedural"
    description: "Executes shell commands and code (Python, etc.) to perform file system operations, data analysis, or web research. This is the primary tool for interacting with the local machine's files and running scripts."
    # This key is the magic. It tells the ChiefOfStaff to inject the 'lmstudio_router'
    # provider configuration into this specialist, so it can configure open-interpreter.
    external_llm_provider_binding: "lmstudio_router"
```

#### Step 3: Create the Specialist Class

Create the specialist file `app/src/specialists/open_interpreter_specialist.py`. The logic is clean and simple: it uses the `llm_adapter` that the `ChiefOfStaff` provides to configure and run the `interpreter` library.

```python
# app/src/specialists/open_interpreter_specialist.py
import logging
from typing import Dict, Any

import litellm
from interpreter import interpreter
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from ..llm.lmstudio_adapter import LMStudioAdapter

logger = logging.getLogger(__name__)

class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A procedural specialist that uses the open-interpreter library.
    """

    SYSTEM_PROMPT = (
        "You are Open Interpreter, a world-class programmer..."
    )

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise RuntimeError("OpenInterpreterSpecialist requires an LLM adapter.")

        # Find the last human message to act on.
        messages = state.get("messages", [])
        last_human_message_content = next(
            (msg.content for msg in reversed(messages) if isinstance(msg, HumanMessage)),
            None
        )
        if not last_human_message_content:
            # Handle case where there's no user command
            return {"messages": [AIMessage(content="No user command found.", name=self.specialist_name)]}

        # Configure the interpreter singleton just-in-time using the injected adapter.
        litellm.disable_cost_logging = True
        model_string = self.llm_adapter.model_name
        if isinstance(self.llm_adapter, LMStudioAdapter):
            model_string = f"openai/{self.llm_adapter.model_name}"

        interpreter.llm.model = model_string
        interpreter.llm.api_base = self.llm_adapter.api_base
        interpreter.llm.api_key = self.llm_adapter.api_key
        interpreter.llm.tool_choice = {"type": "function", "function": {"name": "execute"}}
        interpreter.system_message = self.SYSTEM_PROMPT
        interpreter.auto_run = True
        interpreter.messages = []

        # Execute the command
        response_messages = interpreter.chat(
            last_human_message_content, display=False, stream=False
        )

        # Parse the output to find the result of the code execution.
        computer_outputs = [m['content'] for m in response_messages if m.get('role') == 'computer']
        final_output = "\n".join(computer_outputs) if computer_outputs else "Task completed with no output."

        ai_message = AIMessage(content=final_output, name=self.specialist_name)
        # Signal that the task is complete to trigger the archiver.
        return {"messages": [ai_message], "task_is_complete": True}
```

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
