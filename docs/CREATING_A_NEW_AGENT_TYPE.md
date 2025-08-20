# How to Create a New Specialist Agent

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
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, HumanMessage

# Define your new specialist class. It must inherit from BaseSpecialist.
class CodeWriterSpecialist(BaseSpecialist):
    """A specialist that writes Python code based on a user's request."""

    def __init__(self):
        """Initializes the specialist.

        The most important part of this method is calling the parent class's
        __init__ method with the specialist's name.
        """
        # The specialist_name should be the snake_case version of the class name.
        # This name is used to look up the specialist's configuration in config.yaml.
        super().__init__(specialist_name="code_writer_specialist")

    def execute(self, state: dict) -> dict:
        """This is the main method where your specialist's logic goes.

        It takes the current application state as input and returns a dictionary
        with the updated state.
        """
        # Get the user's most recent message from the state.
        user_input = state["messages"][-1].content

        # 1. Create a standardized request to the Language Model.
        #    This object bundles up the messages and any other parameters
        #    you want to send to the LLM.
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=user_input)]
        )

        # 2. Invoke the LLM adapter.
        #    The self.llm_adapter is automatically configured for this specialist
        #    based on the settings in config.yaml.
        response_data = self.llm_adapter.invoke(request)

        # 3. Process the response from the LLM.
        #    In this case, we are just taking the text response and adding it
        #    to the message history as an AI message.
        ai_message = AIMessage(content=str(response_data['text_response']))

        # 4. Return the updated state.
        #    It is very important to return a dictionary with the updated
        #    "messages" list.
        return {"messages": state["messages"] + [ai_message]}
```

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

```yaml
# config.yaml

specialists:
  # ... other specialists

  code_writer_specialist:
    model: gemini-1.5-flash
    provider: gemini
    prompt_file: code_writer_prompt.md
```

*   `code_writer_specialist`: This key must match the `specialist_name` you set in your specialist's `__init__` method.
*   `model`: The name of the Language Model to use for this specialist. This must be a model defined in the `models` section of `config.yaml`.
*   `provider`: The name of the LLM provider. This must be a provider defined in the `providers` section of `config.yaml`.
*   `prompt_file`: The name of the prompt file you created in the `app/prompts/` directory.

### Step 4: Testing Your New Specialist

After creating your specialist, it's important to test it. You can write a simple unit test in the `app/tests/unit/` directory.

Here is an example test for our `CodeWriterSpecialist`:

```python
# app/tests/unit/test_code_writer_specialist.py

import unittest
from unittest.mock import MagicMock
from app.src.specialists.code_writer_specialist import CodeWriterSpecialist

class TestCodeWriterSpecialist(unittest.TestCase):

    def test_execute(self):
        # Create an instance of the specialist
        specialist = CodeWriterSpecialist()

        # Mock the LLM adapter to avoid making a real API call
        specialist.llm_adapter = MagicMock()
        specialist.llm_adapter.invoke.return_value = {"text_response": "print('Hello, World!')"}

        # Create a sample state
        initial_state = {
            "messages": [{"role": "user", "content": "Write a hello world program in Python"}]
        }

        # Execute the specialist
        result_state = specialist.execute(initial_state)

        # Check that the AI message was added to the state
        self.assertEqual(len(result_state["messages"]), 2)
        self.assertEqual(result_state["messages"][-1].content, "print('Hello, World!')")

if __name__ == '__main__':
    unittest.main()

```

To run the tests, simply run `pytest` from the root directory.

## Creating a Wrapped Specialist

In addition to creating specialists from scratch, you can also wrap existing, externally-sourced agents. This is useful for integrating third-party agents or agents from other repositories into your workflow.

### Step 1: Create the Wrapper Specialist File

Create a new Python file in `app/src/specialists/`. This class must inherit from `WrappedSpecialist`.

```python
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
        return {"messages": state["messages"] + [ai_message]}
```

### Step 2: Configure the Wrapped Specialist in `config.yaml`

Add a new entry to your `config.yaml` file under the `specialists` key. This entry must include `type: wrapped` and a `source` key pointing to the entry point of the external agent.

```yaml
specialists:
  open_swe_specialist:
    type: wrapped
    source: "./open-swe/agent/run.py"
    description: "A specialist that wraps the open-swe agent for software engineering tasks."
```

## Conclusion

That's it! You have successfully created a new specialist agent. The `ChiefOfStaff` class will automatically discover and integrate your new specialist at runtime. By following these steps, you can extend the system with new capabilities. Remember to always keep your specialists focused on a single task to maintain a clean and modular architecture.
