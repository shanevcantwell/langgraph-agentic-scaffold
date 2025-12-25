# app/src/specialists/default_responder_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class DefaultResponderSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, conversational response to the user's prompt.
    It is intended for simple, single-turn interactions where no other specialist's
    tools are required. It signals task completion after it runs.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"Initialized {self.specialist_name}")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response and signals that the task is complete.
        """
        # =============================================================================
        # TEMPORARY FIX: Exit Interview Pattern (Issue #7, ADR-CORE-036)
        #
        # This is a stopgap until a proper ExitInterviewSpecialist is implemented.
        # DefaultResponder now checks if artifacts were produced that satisfy the
        # user's request, and presents them instead of generating a generic response.
        #
        # TODO: Replace with dedicated ExitInterviewSpecialist per ADR-CORE-036
        # =============================================================================
        artifacts = state.get("artifacts", {})

        # Check for key deliverable artifacts and present them directly
        if "system_plan" in artifacts:
            plan = artifacts["system_plan"]
            plan_summary = plan.get("plan_summary", "See details below")
            plan_steps = plan.get("execution_steps", [])

            if plan_steps:
                steps_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan_steps))
                text_response = f"Here's the plan I created:\n\n**{plan_summary}**\n\nSteps:\n{steps_text}"
            else:
                text_response = f"Here's the plan I created:\n\n**{plan_summary}**"

            logger.info("DefaultResponder: Presenting system_plan artifact (Exit Interview pattern)")

            ai_message = create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=text_response,
            )
            return {
                "messages": [ai_message],
                "task_is_complete": True,
                "scratchpad": {"user_response_snippets": [text_response]}
            }
        # =============================================================================
        # END TEMPORARY FIX
        # =============================================================================

        # The DefaultResponder's role is purely conversational. It should only
        # consider the user's messages and its own previous responses to create a
        # clean conversational context, ignoring orchestration messages from other
        # specialists.
        messages: list[BaseMessage] = [
            msg for msg in state.get("messages", [])
            if isinstance(msg, HumanMessage) or (isinstance(msg, AIMessage) and msg.name == self.specialist_name)
        ]

        # The specialist should act on the full, current state of the conversation.
        # Its system prompt guides it to focus on the most recent message.
        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)

        text_response = response_data.get("text_response")
        if not text_response:
            # If the LLM fails to provide a text response, provide a more informative fallback.
            raw_response_content = response_data.get("raw_response_content", "No raw response available.")
            error_message = f"I was unable to provide a response. The LLM returned an empty text response. Raw output: {raw_response_content}"
            text_response = error_message

        logger.info(f"DefaultResponderSpecialist generated response: '{text_response}'")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=text_response,
        )

        # Per the termination sequence, this specialist signals completion
        # by adding its final message and setting the `task_is_complete` flag.
        return {
            "messages": [ai_message],
            "task_is_complete": True,
            "scratchpad": {"user_response_snippets": [text_response]}
        }