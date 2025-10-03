# app/src/specialists/end_specialist.py
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import AIMessage, ToolMessage
from .response_synthesizer_specialist import ResponseSynthesizerSpecialist
from .archiver_specialist import ArchiverSpecialist
from ..llm.factory import AdapterFactory
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class EndSpecialist(BaseSpecialist):
    """
    A procedural specialist that acts as a "Finalizer" or "Coordinator" for the
    workflow. It ensures the standard termination sequence (Synthesize, Archive)
    is executed deterministically.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any], adapter_factory: AdapterFactory):
        super().__init__(specialist_name, specialist_config)
        synthesizer_config = specialist_config.get("response_synthesizer_specialist", {})
        archiver_config = specialist_config.get("archiver_specialist", {})

        self.synthesizer = ResponseSynthesizerSpecialist("response_synthesizer_specialist", synthesizer_config)
        self.archiver = ArchiverSpecialist("archiver_specialist", archiver_config)

        # The synthesizer is an LLM specialist and requires an adapter. We use the
        # passed-in factory to create one for it, using its own name and config.
        # This is a special case because EndSpecialist is a procedural coordinator
        # that internally manages another LLM-based specialist.
        if synthesizer_config and synthesizer_config.get("type") == "llm":
            prompt_file = synthesizer_config.get("prompt_file")
            system_prompt = load_prompt(prompt_file) if prompt_file else ""
            self.synthesizer.llm_adapter = adapter_factory.create_adapter("response_synthesizer_specialist", system_prompt)
            logger.info("EndSpecialist successfully created LLM adapter for its internal ResponseSynthesizer.")

        logger.info("---INITIALIZED EndSpecialist Coordinator---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrates the final synthesis and archiving steps.
        """
        logger.info("--- EndSpecialist: Beginning final termination sequence. ---")

        current_state = state.copy()

        # Per DEVELOPERS_GUIDE.md, the EndSpecialist must handle cases where no
        # user-facing snippets were generated.
        scratchpad = current_state.get("scratchpad", {})
        if not scratchpad.get("user_response_snippets"):
            logger.warning("EndSpecialist: No user_response_snippets found. Generating fallback response.")
            messages = current_state.get("messages", [])
            last_message = messages[-1] if messages else None

            # If the last action was a tool, present its output directly.
            if isinstance(last_message, ToolMessage):
                fallback_content = f"The task finished with the following result:\n\n```\n{last_message.content}\n```"
            else:
                fallback_content = "The workflow has completed."

            current_state.setdefault("artifacts", {})["final_user_response.md"] = fallback_content
            logger.info("EndSpecialist: Fallback response created. Skipping synthesizer.")

        if not current_state.get("artifacts", {}).get("final_user_response.md"):
            logger.info("EndSpecialist: Synthesizing final response.")
            synthesis_updates = self.synthesizer._execute_logic(current_state)
            current_state["messages"] = current_state.get("messages", []) + synthesis_updates.get("messages", [])
            current_state.setdefault("artifacts", {}).update(synthesis_updates.get("artifacts", {}))
            current_state.setdefault("scratchpad", {}).update(synthesis_updates.get("scratchpad", {}))
        else:
            logger.info("EndSpecialist: Final response already exists. Skipping synthesis.")

        logger.info("EndSpecialist: Archiving interaction.")
        archival_updates = self.archiver._execute_logic(current_state)

        return archival_updates