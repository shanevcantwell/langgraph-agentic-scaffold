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
        # The constructor is now clean and has no side effects.
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Generates and executes code based on the user's request.
        """
        # --- Lazy Load and Configure the Interpreter ---
        # By importing here, we contain all side effects (network calls, etc.)
        # to the execution phase of this specialist only.
        try:
            from interpreter import interpreter
            # Configure the interpreter instance just-in-time.
            # By setting the context_window to 0, we effectively disable the
            # interpreter's internal LLM, preventing it from making unwanted
            # litellm calls. This forces it to act as a pure code executor.
            interpreter.auto_run = True
            interpreter.llm.context_window = 0
        except ImportError:
            logger.error(
                "The 'open-interpreter' package is not installed. "
                "Please add 'open-interpreter' to pyproject.toml and run './scripts/sync-reqs.sh'."
            )
            return {"error": "Required package 'open-interpreter' is not installed."}

        if not self.llm_adapter:
            raise RuntimeError(
                "OpenInterpreterSpecialist requires an LLM adapter to generate code. "
                "Ensure it is bound to a provider in user_settings.yaml."
            )

        messages = state.get("messages", [])
        
        last_human_message_content = next(
            (msg.content for msg in reversed(messages) if isinstance(msg, HumanMessage)),
            "No specific user instruction found. Review the conversation history and decide on the next code action."
        )

        # --- Phase 1: Plan the Code to Execute ---
        logger.info("Phase 1: Generating code execution plan...")
        planning_prompt = (
            "Based on the following user request and conversation history, your task is to generate a single, "
            "self-contained code block to be executed by the open-interpreter. "
            "You must respond by calling the 'CodeExecutionParams' tool.\n\n"
            f"USER REQUEST: {last_human_message_content}"
        )
        
        request = StandardizedLLMRequest(
            messages=messages + [HumanMessage(content=planning_prompt)],
            tools=[CodeExecutionParams]
        )
        
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.error("LLM failed to generate a valid code execution plan. Aborting.")
            return {"error": "OpenInterpreterSpecialist's LLM failed to produce a valid code plan."}

        try:
            code_params = CodeExecutionParams(**tool_calls[0]['args'])
        except Exception as e:
            logger.error(f"Failed to parse LLM tool call into CodeExecutionParams: {e}", exc_info=True)
            return {"error": f"Failed to parse code plan: {e}"}

        logger.info(f"Phase 1 Complete. Plan: execute '{code_params.language}' code.")

        # --- Phase 2: Execute the Code ---
        logger.info(f"Phase 2: Executing code...\n---\n{code_params.code}\n---")
        
        # The `interpreter.run()` method is deprecated. The new `chat()` method
        # can be used to execute code directly by passing it in a specific format.
        # This preserves our two-phase "plan then execute" model.
        interpreter.messages = [] # Clear previous messages
        response_chunks = interpreter.chat(f"Please execute this {code_params.language} code:\n```{code_params.language}\n{code_params.code}\n```", display=False, stream=True)
        
        # The `chat` method returns a generator. We need to consume it to get the results.
        # The final output is now stored in the `interpreter.messages` list.
        for _ in response_chunks:
            pass
        
        outputs = [msg.get('content', '') for msg in interpreter.messages if msg.get('role') == 'computer' and msg.get('type') == 'output']
        final_output = "\n".join(outputs) if outputs else "Code executed with no output."
        
        logger.info(f"Phase 2 Complete. Execution output: {final_output[:500]}...")

        # --- Create a Standardized Response ---
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have executed the following {code_params.language} code:\n\n```\n{code_params.code}\n```\n\n**Result:**\n{final_output}",
        )
        
        return {"messages": [ai_message], "task_is_complete": True}
