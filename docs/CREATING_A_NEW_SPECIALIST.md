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
        ai_response_content = response_data.get("text_response", "I am unable to provide a response at this time.")
        ai_message = AIMessage(content=ai_response_content)

        # 4. Return the updated state.
        #    It is critical to only return the *new* messages you want to add
        #    to the history. The graph is configured to append these messages
        #    to the existing list of messages in the state.
        return {"messages": [ai_message]}

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

*   **Programmatic Task Completion:** Some specialists are designed to produce a final answer. To signal that the overall task is finished, the specialist should include `task_is_complete: True` in the state it returns. The `RouterSpecialist` will see this flag and route the graph to `END`.
    *   **Example:** See `TextAnalysisSpecialist`, which sets this flag to `True` if it determines it has produced the final answer.

For a deeper understanding of these patterns, refer to the **"Agentic Robustness Patterns"** section in the **Developer's Guide**.

## Creating a Wrapped Specialist

Wrapped specialists rely on external, third-party code. To keep the project clean and avoid checking in external repositories, this scaffold uses a conventional directory: `external/`.

The `external/` directory at the project root is the designated location for cloning any third-party agent repositories. Its contents are ignored by Git (via `.gitignore`), so you can safely manage external code without cluttering your project's history.

**To add an external agent:**

1.  Clone the external agent's repository into the `external/` directory. For example, to add the `open-swe` agent:
    ```sh
    git clone https://github.com/sweepai/open-swe.git external/open-swe
2.  In your `config.yaml`, set the `source` path for your wrapped specialist to point to the agent's entrypoint script within the `external/` directory.

---

In addition to creating specialists from scratch, you can also wrap existing, externally-sourced agents. This is useful for integrating third-party agents or agents from other repositories into your workflow.

### Step 1: Create the Wrapper Specialist File

Create a new Python file in `app/src/specialists/`. This class must inherit from `WrappedSpecialist`.

# app/src/specialists/open_swe_specialist.py

from .wrapped_specialist import WrappedSpecialist
from langchain_core.messages import AIMessage

class OpenSweSpecialist(WrappedSpecialist):
    """A wrapper specialist for the open-swe agent."""

    def _translate_state_to_input(self, state: dict) -> any:
        """Translates the GraphState to the open-swe agent's input format."""
        return state["messages"][-1].content

    def _translate_output_to_state(self, state: dict, output: any) -> dict:
        """Translates the open-swe agent's output back to the GraphState format."""
        ai_message = AIMessage(content=str(output))
        return {"messages": [ai_message]}

### Step 2: Configure the Wrapped Specialist in `config.yaml`

Add a new entry to your `config.yaml` file under the `specialists` key. This entry must include `type: wrapped` and a `source` key pointing to the entry point of the external agent.

Following the convention above, the configuration for `open_swe_specialist` would look like this:
specialists:
  open_swe_specialist:
    type: wrapped
    source: "./external/open-swe/agent/run.py" # Path relative to project root
    description: "A specialist that wraps the open-swe agent for software engineering tasks."

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
