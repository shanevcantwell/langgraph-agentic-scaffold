"""
DialogueSpecialist: Human-in-the-Loop Clarification Handler

ADR-CORE-018: Presents clarification questions to the user when TriageArchitect
determines the request is ambiguous (ASK_USER actions in ContextPlan).

Flow:
    1. FacilitatorSpecialist executes automated actions (READ_FILE, RESEARCH, etc.)
    2. DialogueSpecialist checks if ASK_USER actions remain
    3. If yes: formats questions, calls interrupt(), waits for user response
    4. If no: no-op pass-through to Router

Key Distinction:
    - DialogueSpecialist: Active, directed - "I need X, Y, Z from you to proceed"
    - DefaultResponderSpecialist: Passive fallback - "Generic response because nothing else fit"
"""
import logging
from typing import Dict, Any, List

from langgraph.types import interrupt

from .base import BaseSpecialist
from ..interface.context_schema import ContextPlan, ContextActionType

logger = logging.getLogger(__name__)


class DialogueSpecialist(BaseSpecialist):
    """
    Handles human-in-the-loop clarification when TriageArchitect identifies
    ambiguity in the user's request.

    Uses LangGraph's dynamic interrupt() to pause graph execution and
    send a clarification payload to the client. When the user responds,
    the graph resumes from the interrupt point.
    """

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Check for ASK_USER actions and trigger interrupt if present.

        Returns empty dict (no-op) if no clarification needed.
        """
        artifacts = state.get("artifacts", {})
        context_plan_data = artifacts.get("context_plan")

        # No plan to check - no-op
        if not context_plan_data:
            logger.debug("DialogueSpecialist: No context_plan in artifacts, passing through")
            return {}

        try:
            context_plan = ContextPlan(**context_plan_data)
        except Exception as e:
            logger.error(f"DialogueSpecialist: Failed to parse ContextPlan: {e}")
            return {}

        # Extract ASK_USER actions
        ask_user_actions = [
            action for action in context_plan.actions
            if action.type == ContextActionType.ASK_USER
        ]

        # No ASK_USER actions - no-op
        if not ask_user_actions:
            logger.debug("DialogueSpecialist: No ASK_USER actions in plan, passing through")
            return {}

        # Format questions with any gathered context
        gathered_context = artifacts.get("gathered_context", "")
        questions = self._format_questions(ask_user_actions, gathered_context)

        logger.info(f"DialogueSpecialist: Triggering interrupt with {len(ask_user_actions)} questions")

        # Dynamic interrupt - halts graph, sends payload to client
        # When graph.resume() is called with user input, execution continues here
        user_answer = interrupt({
            "clarification_required": True,
            "questions": questions,
            "question_count": len(ask_user_actions),
            "gathered_context_preview": gathered_context[:500] if gathered_context else None,
            "triage_reasoning": context_plan.reasoning
        })

        # Resume point - user_answer contains the response from /resume endpoint
        logger.info(f"DialogueSpecialist: Resumed with user clarification: {user_answer[:100] if user_answer else 'None'}...")

        return {
            "artifacts": {
                "user_clarification": user_answer
            },
            "scratchpad": {
                "dialogue_complete": True,
                "clarification_provided": True
            }
        }

    def _format_questions(
        self,
        ask_user_actions: List,
        gathered_context: str
    ) -> List[Dict[str, str]]:
        """
        Format ASK_USER actions into a structured list of questions.

        Each question includes:
        - question: The clarification needed
        - reason: Why this information is needed (from action.description)

        Args:
            ask_user_actions: List of ContextAction with type=ASK_USER
            gathered_context: Any context already gathered by Facilitator

        Returns:
            List of question dictionaries for the interrupt payload
        """
        questions = []

        for action in ask_user_actions:
            question_entry = {
                "question": action.target,
                "reason": action.description
            }
            questions.append(question_entry)

        # If we have gathered context, add a note that context was found
        if gathered_context:
            logger.info(
                f"DialogueSpecialist: Including {len(gathered_context)} chars of gathered context "
                "to help user answer questions"
            )

        return questions
