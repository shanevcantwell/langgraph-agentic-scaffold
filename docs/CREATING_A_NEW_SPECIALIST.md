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

The key is a clean separation of concerns. The specialist class itself contains the integration logic, while the `config.yaml` file provides all the necessary configuration, including which LLM the external library should use.

1.  **Install the Library:** The external tool is installed as a standard Python dependency via `pip-tools`.
2.  **Configure in `config.yaml`:** You register the specialist with `type: "procedural"`. Crucially, you add an `external_llm_provider_binding` key to tell the specialist which `llm_provider` configuration it should use for the external library.
3.  **Create the Specialist Class:** The specialist inherits from `BaseSpecialist`. It uses a property-setter pattern to receive its configuration from the `ChiefOfStaff`. This allows it to configure the external library *after* it has been instantiated.
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

Create the specialist file `app/src/specialists/open_interpreter_specialist.py`. The key is the property-setter pattern, which allows the `ChiefOfStaff` to inject dependencies in a controlled order.

```python
# app/src/specialists/open_interpreter_specialist.py
import logging
from typing import Dict, Any, Optional

from interpreter import interpreter
from langchain_core.messages import AIMessage

from .base import BaseSpecialist

logger = logging.getLogger(__name__)

class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A procedural specialist that uses the open-interpreter library to execute code.
    It is configured via the `external_llm_provider_binding` in config.yaml.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        self._specialist_config: Optional[Dict[str, Any]] = None
        # This will be injected by the ChiefOfStaff *before* specialist_config is set.
        self.external_provider_config: Optional[Dict[str, Any]] = None

    @property
    def specialist_config(self) -> Optional[Dict[str, Any]]:
        return self._specialist_config

    @specialist_config.setter
    def specialist_config(self, config: Dict[str, Any]):
        """
        Sets the specialist configuration and triggers the interpreter setup.
        This method is called by the ChiefOfStaff during its loading process.
        """
        self._specialist_config = config
        self._configure_interpreter()
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _configure_interpreter(self):
        """Configures the open-interpreter singleton based on the injected provider config."""
        if not self.external_provider_config:
            raise ValueError("OpenInterpreter's external_provider_config was not injected.")
        
        provider_config = self.external_provider_config
        binding_key = self.specialist_config.get("external_llm_provider_binding")

        # Configure the interpreter singleton with the correct API details
        interpreter.auto_run = True
        interpreter.model = provider_config.get("api_identifier")
        
        provider_type = provider_config.get("type")
        if provider_type == "lmstudio" or provider_type == "ollama":
            interpreter.api_base = provider_config.get("base_url")
            interpreter.api_key = "lm-studio"  # Can be any non-empty string
        elif provider_type == "gemini":
            interpreter.api_key = provider_config.get("api_key")
        
        interpreter.system_message = (
            "You are Open Interpreter, a world-class programmer that can complete any task by executing code. "
            "You are in a sandboxed environment. You can only read/write files in the './workspace' directory. "
            "When you are done, respond with a summary of what you have done."
        )
        logger.info(f"OpenInterpreter configured to use LLM provider: {binding_key}")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        last_message = state["messages"][-1].content
        interpreter.messages = [] # Reset history for each run
        response_messages = interpreter.chat(last_message, display=False, stream=False)
        
        assistant_responses = [m['content'] for m in response_messages if m['role'] == 'assistant']
        final_output = "\n".join(assistant_responses) if assistant_responses else "Task completed with no output."
        
        ai_message = AIMessage(content=final_output, name=self.specialist_name)
        return {"messages": [ai_message]}
```

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
