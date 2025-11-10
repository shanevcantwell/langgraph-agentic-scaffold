# app/src/specialists/open_interpreter_specialist.py

import logging
from typing import Dict, Any

# DO NOT IMPORT 'interpreter' HERE AT THE MODULE LEVEL
from langchain_core.messages import HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt
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
        prompt_file = self.specialist_config.get("prompt_file")
        if not prompt_file:
            raise ValueError("OpenInterpreterSpecialist requires a 'prompt_file' in its configuration.")
        planning_prompt = load_prompt(prompt_file)

        request = StandardizedLLMRequest(
            messages=[last_human_message, HumanMessage(content=planning_prompt)],
            tools=[CodeExecutionParams],
            # This specialist's prompt demands a tool call, so we must enforce it.
            # This ensures the adapter uses the strongest possible mechanism to get a tool call.
            force_tool_call=True
        )

        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.error("LLM failed to generate a valid code execution plan. Aborting.")
            return None

        try:
            return CodeExecutionParams(**tool_calls[0]['args'])
        except Exception as e:
            error_msg = f"Failed to parse LLM tool call into CodeExecutionParams: {e}"
            logger.error(error_msg, exc_info=True)
            self._planning_error = error_msg  # Store for use in error response
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
        self._planning_error = None  # Reset any previous error
        code_params = self._plan_code(last_human_message)
        if not code_params:
            error_msg = "OpenInterpreterSpecialist's LLM failed to produce a valid code plan."
            if hasattr(self, '_planning_error') and self._planning_error:
                error_msg += f" {self._planning_error}"
            return {"error": error_msg}

        # Phase 2: Execute
        try:
            final_output = self._execute_code(code_params)
        except Exception as e:
            error_msg = f"Execution failed: {str(e)}"
            logger.error(f"Code execution error: {error_msg}")
            return {"error": error_msg}

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
