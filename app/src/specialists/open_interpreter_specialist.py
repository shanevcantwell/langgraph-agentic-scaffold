# app/src/specialists/open_interpreter_specialist.py

import logging
from typing import Dict, Any
# Import litellm to configure it directly
import litellm
from interpreter import interpreter
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.lmstudio_adapter import LMStudioAdapter

logger = logging.getLogger(__name__)


class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A procedural specialist that uses the open-interpreter library to execute code.
    """

    SYSTEM_PROMPT = (
        "You are Open Interpreter, a world-class programmer that can complete any task by executing code. "
        "You are in a sandboxed environment. You can only read/write files in the './workspace' directory. "
        "When you are done, respond with a summary of what you have done."
    )

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _perform_pre_flight_checks(self) -> bool:
        """Checks if the 'open-interpreter' package is installed."""
        try:
            import interpreter
            logger.info("'open-interpreter' package found. OpenInterpreterSpecialist is enabled.")
            return True
        except ImportError:
            logger.error(
                "The 'open-interpreter' package is not installed. "
                "OpenInterpreterSpecialist will be disabled. "
                "Please install it by adding 'open-interpreter' to your pyproject.toml "
                "and running './scripts/sync-reqs.sh'."
            )
            return False

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise RuntimeError(
                "OpenInterpreterSpecialist requires an LLM adapter. "
                "Ensure it is bound to an LLM provider in user_settings.yaml."
            )

        # Find the last human message to use as the prompt. This is more robust
        # than just taking the last message, which is often a routing message
        # from the RouterSpecialist.
        messages = state.get("messages", [])
        last_human_message_content = next(
            (msg.content for msg in reversed(messages) if isinstance(msg, HumanMessage)),
            None
        )

        if not last_human_message_content:
            logger.warning("OpenInterpreterSpecialist could not find a human message to execute. Skipping.")
            ai_message = AIMessage(
                content="I was asked to run, but I could not find a specific command from the user to execute. Please provide a clear instruction.",
                name=self.specialist_name
            )
            return {"messages": [ai_message]}

        # --- Configure litellm for local model usage ---
        # Disable cost logging to prevent noisy errors for unmapped local models.
        litellm.disable_cost_logging = True

        # --- Configure the interpreter singleton for this execution ---
        # The open-interpreter library uses a global singleton. We must configure it
        # before each use to ensure it has the correct settings from our adapter.
        # The logic for constructing the model string for litellm is now contained
        # here, based on the type of the adapter, which is much cleaner than
        # checking the provider type from the config.
        model_string = self.llm_adapter.model_name
        if isinstance(self.llm_adapter, LMStudioAdapter):
            model_string = f"openai/{self.llm_adapter.model_name}"

        # The open-interpreter library nests its LLM configuration under the 'llm' attribute.
        # We must set the model, api_base, and api_key on this nested object for the
        # settings to be recognized by the `chat` method.
        interpreter.llm.model = model_string
        interpreter.llm.api_base = self.llm_adapter.api_base
        interpreter.llm.api_key = self.llm_adapter.api_key
        # Force the model to use the 'execute' tool by name. This is a more specific
        # and robust way to "lock down" the specialist than simply using "required".
        # It prevents the model from trying to call a non-existent tool, mirroring
        # the more advanced patterns seen in the system's adapters.
        interpreter.llm.tool_choice = {"type": "function", "function": {"name": "execute"}}
        interpreter.system_message = self.SYSTEM_PROMPT
        interpreter.auto_run = True
        interpreter.messages = []  # Reset history for each run

        logger.info(f"Executing prompt with Open Interpreter: {last_human_message_content[:100]}...")
        # The chat method does not accept configuration arguments; they must be set on the singleton.
        response_messages = interpreter.chat(
            last_human_message_content,
            display=False,
            stream=False,
        )

        # --- Intelligent Parsing of Open Interpreter's Output ---
        # The 'open-interpreter' library returns a rich transcript. We need to parse it
        # to find the most useful information for the user, which is typically the
        # output from the code execution, not the code itself or conversational filler.

        # Look for the output from the 'computer' role, which contains stdout/stderr.
        computer_outputs = [m['content'] for m in response_messages if m.get('role') == 'computer' and m.get('type') == 'output']

        # If there's direct output, use that as the primary response.
        if computer_outputs:
            final_output = "\n".join(computer_outputs)
        else:
            # If there's no direct computer output, fall back to the assistant's
            # final summary message. This handles cases where the model summarizes
            # its actions without direct code output.
            assistant_summaries = [m['content'] for m in response_messages if m.get('role') == 'assistant' and m.get('type') == 'message']
            if assistant_summaries:
                final_output = "\n".join(assistant_summaries)
            else:
                # As a last resort, join all assistant content. This was the previous behavior.
                assistant_content = [m['content'] for m in response_messages if m.get('role') == 'assistant']
                final_output = "\n".join(assistant_content) if assistant_content else "Task completed with no user-facing output."

        logger.info(f"Open Interpreter finished execution. Parsed Output: {final_output[:200]}...")
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=final_output,
        )
        # Signal to the router that this task is complete, which will trigger the
        # archiver to create a final report.
        return {"messages": [ai_message], "task_is_complete": True}