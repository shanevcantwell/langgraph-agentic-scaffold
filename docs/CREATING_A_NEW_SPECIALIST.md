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

## Advanced: Creating a `WrappedCodeSpecialist`

A `WrappedCodeSpecialist` allows you to integrate powerful, third-party Python libraries or agents into the scaffold by creating a simple "wrapper" class. This is a great way to leverage existing tools like `open-interpreter` without having to rewrite their logic.

### How it Works

1.  **Install the Library:** The external tool is installed as a standard Python dependency via `pip`.
2.  **Create a Wrapper Class:** You create a small Python class in the `external_agents/` directory. This class must have a `run(self, input)` method. Its job is to translate the simple input from your specialist into the specific API calls required by the external library and return a simple output.
3.  **Create the Specialist:** You create a specialist class that inherits from `WrappedCodeSpecialist`. This specialist is very thin; it only needs to translate the graph's state to the input for your wrapper's `run` method, and translate the wrapper's output back into the graph's state.
4.  **Configure:** You register the specialist in `config.yaml` with `type: "wrapped_code"`, pointing to your wrapper class.

### Example: Wrapping `open-interpreter`

Let's walk through wrapping the `open-interpreter` library, which allows an LLM to execute code locally.

#### Step 1: Install the Dependency

First, add `open-interpreter` to your `pyproject.toml` and run the sync script (`./scripts/sync-reqs.sh`) to install it.

#### Step 2: Create the Wrapper Class

Create a new file `external_agents/OpenInterpreter/open_interpreter_wrapper.py`. This class will act as the bridge to the `open-interpreter` library.

```python
# external_agents/OpenInterpreter/open_interpreter_wrapper.py
from interpreter import interpreter

class OpenInterpreterAgent:
    def __init__(self):
        interpreter.auto_run = True
        interpreter.system_message = "You are Open Interpreter..." # (abbreviated for docs)

    def run(self, prompt: str) -> str:
        interpreter.messages = []
        messages = interpreter.chat(prompt)
        assistant_responses = [m['content'] for m in messages if m['role'] == 'assistant']
        return "\n".join(assistant_responses) if assistant_responses else "Task completed."
```

### Step 3: Create the Wrapper Specialist File

Create a new Python file in `app/src/specialists/`. This class must inherit from `WrappedCodeSpecialist`.

```python
# app/src/specialists/open_interpreter_specialist.py
from typing import Dict, Any
from .wrapped_code_specialist import WrappedCodeSpecialist
from langchain_core.messages import AIMessage

class OpenInterpreterSpecialist(WrappedCodeSpecialist):
    """A wrapper specialist for the Open Interpreter agent."""

    def _translate_state_to_input(self, state: Dict[str, Any]) -> Any:
        return state["messages"][-1].content

    def _translate_output_to_state(self, state: dict, output: Any) -> Dict[str, Any]:
        ai_message = AIMessage(content=str(output), name=self.specialist_name)
        return {"messages": [ai_message]}
```

### Step 4: Configure the `WrappedCodeSpecialist` in `config.yaml`

Add a new entry to your `config.yaml` file under the `specialists` key. This entry must include `type: "wrapped_code"`, a `wrapper_path` key pointing to the Python file containing your wrapper class, and the `class_name` to instantiate.

specialists:
  open_interpreter_specialist:
    type: "wrapped_code"
    wrapper_path: "./external_agents/OpenInterpreter/open_interpreter_wrapper.py" # Path to the wrapper class file, relative to the project root.
    class_name: "OpenInterpreterAgent"
    description: "A powerful specialist that can execute code (Python, Shell, etc.) on the local machine to perform a wide variety of tasks, including file manipulation, data analysis, and web research. Use for complex, multi-step tasks that require coding."

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
