# app/src/specialists/end_specialist.py
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from .archiver_specialist import ArchiverSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class EndSpecialist(BaseSpecialist):
    """
    A hybrid coordinator that manages the Coordinated Completion Sequence.
    It synthesizes a final user response and archives the interaction.

    Architectural Note: This specialist directly performs response synthesis
    using its own LLM adapter rather than delegating to a separate specialist.
    This simplifies configuration and aligns with the principle that workflow
    completion is a single, atomic operation owned by this coordinator.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

        # Load the synthesis prompt (will be used when adapter is attached)
        self.synthesis_prompt_file = specialist_config.get("synthesis_prompt_file", "response_synthesizer_prompt.md")

        # Initialize archiver with its config
        archiver_config = specialist_config.get("archiver_config", {
            "type": "procedural",
            "archive_path": "./logs/archive",
            "pruning_strategy": "count",
            "pruning_max_count": 50
        })
        self.archiver = ArchiverSpecialist("archiver_specialist", archiver_config)

        logger.info("---INITIALIZED EndSpecialist Coordinator---")

    def _synthesize_response(self, state: Dict[str, Any]) -> str:
        """
        Synthesizes a final, user-facing response from accumulated snippets.
        This is the inline implementation of what ResponseSynthesizerSpecialist did.
        """
        scratchpad = state.get("scratchpad", {})
        raw_snippets = scratchpad.get("user_response_snippets", [])

        # Filter out empty snippets
        user_response_snippets = [s for s in raw_snippets if str(s).strip()]

        # If no snippets, generate fallback
        if not user_response_snippets:
            logger.warning("EndSpecialist: No user_response_snippets found for synthesis.")
            messages = state.get("messages", [])
            last_message = messages[-1] if messages else None

            if isinstance(last_message, ToolMessage):
                return f"The task finished with the following result:\n\n```\n{last_message.content}\n```"
            elif isinstance(last_message, AIMessage) and last_message.content:
                return last_message.content
            else:
                return "The workflow has completed its tasks, but no specific output was generated to display."

        # Concatenate snippets for LLM synthesis
        combined_snippets = "\n\n---\n\n".join(str(s) for s in user_response_snippets)

        # Call LLM for synthesis
        messages = [HumanMessage(content=combined_snippets)]
        request = StandardizedLLMRequest(messages=messages)

        try:
            response_data = self.llm_adapter.invoke(request)
            synthesized_response = response_data.get("text_response")

            if not synthesized_response:
                logger.error(f"EndSpecialist: LLM synthesis failed. Raw output: {response_data.get('raw_response_content', 'N/A')}")
                return "I was unable to generate a final response based on the preceding actions."

            return synthesized_response
        except Exception as e:
            logger.error(f"EndSpecialist: Exception during synthesis: {e}", exc_info=True)
            return "An error occurred while generating the final response."

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrates the Coordinated Completion Sequence: synthesis and archiving.
        """
        logger.info("--- EndSpecialist: Beginning Coordinated Completion Sequence. ---")

        current_state = state.copy()

        # Check for explicit termination reason (e.g., from loop detection)
        termination_reason = current_state.get("scratchpad", {}).get("termination_reason")
        
        # Check for clarification questions from Triage (#179 reject-with-cause)
        triage_actions = current_state.get("scratchpad", {}).get("triage_actions", [])
        clarification_questions = [
            f"- {a['target']}" for a in triage_actions
            if a.get("type") == "ask_user" and a.get("target")
        ]

        if termination_reason:
            logger.warning(f"EndSpecialist: Using explicit termination reason: {termination_reason}")
            synthesized_response = termination_reason
        elif clarification_questions:
            logger.info("EndSpecialist: Presenting clarification questions to user.")
            synthesized_response = "I need some clarification before I can proceed:\n\n" + "\n".join(clarification_questions)
        # Check if final response already exists
        elif current_state.get("artifacts", {}).get("final_user_response.md"):
            logger.info("EndSpecialist: Final response already exists. Skipping synthesis.")
            synthesized_response = current_state["artifacts"]["final_user_response.md"]
        else:
            # Perform synthesis
            logger.info("EndSpecialist: Synthesizing final response from snippets.")
            synthesized_response = self._synthesize_response(current_state)

        # Create AI message for the synthesis
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=synthesized_response,
            additional_kwargs={"synthesized_from_snippets": True}
        )

        # Update state with synthesized response
        current_state.setdefault("messages", []).append(ai_message)
        current_state.setdefault("artifacts", {})["final_user_response.md"] = synthesized_response
        current_state.setdefault("scratchpad", {})["user_response_snippets"] = []  # Clear snippets

        # ADR-CORE-045: Skip archiver in subagent mode — parent archives the overall run
        if current_state.get("scratchpad", {}).get("subagent"):
            logger.info("EndSpecialist: Subagent mode — skipping archiver.")
            return current_state

        # Archive the interaction
        logger.info("EndSpecialist: Archiving interaction.")
        archival_updates = self.archiver._execute_logic(current_state)

        return archival_updates
