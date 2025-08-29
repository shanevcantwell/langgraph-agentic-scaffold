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

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
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
            # This error will trigger if the specialist is not bound to an LLM provider
            # in user_settings.yaml, as it requires an LLM to function.
            raise RuntimeError("OpenInterpreterSpecialist requires an LLM adapter. Ensure it is bound to a provider in user_settings.yaml.")

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
        model_string = self.llm_adapter.model_name
        if isinstance(self.llm_adapter, LMStudioAdapter):
            model_string = f"openai/{self.llm_adapter.model_name}"

        interpreter.llm.model = model_string
        interpreter.llm.api_base = self.llm_adapter.api_base
        interpreter.llm.api_key = self.llm_adapter.api_key
        interpreter.llm.tool_choice = {"type": "function", "function": {"name": "execute"}}
        interpreter.system_message = self.SYSTEM_PROMPT
        interpreter.auto_run = True
        interpreter.messages = []  # Reset history for each run

        logger.info(f"Executing prompt with Open Interpreter: {last_human_message_content[:100]}...")
        response_messages = interpreter.chat(
            last_human_message_content,
            display=False,
            stream=False,
        )

        # --- Intelligent Parsing of Open Interpreter's Output ---
        computer_outputs = [m['content'] for m in response_messages if m.get('role') == 'computer' and m.get('type') == 'output']

        if computer_outputs:
            final_output = "\n".join(computer_outputs)
        else:
            assistant_summaries = [m['content'] for m in response_messages if m.get('role') == 'assistant' and m.get('type') == 'message']
            if assistant_summaries:
                final_output = "\n".join(assistant_summaries)
            else:
                assistant_content = [m['content'] for m in response_messages if m.get('role') == 'assistant']
                final_output = "\n".join(assistant_content) if assistant_content else "Task completed with no user-facing output."

        logger.info(f"Open Interpreter finished execution. Parsed Output: {final_output[:200]}...")
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=final_output,
        )
        return {"messages": [ai_message], "task_is_complete": True}