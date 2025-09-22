# app/src/specialists/end_specialist.py
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import AIMessage
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
        # We need instances of the specialists whose logic we are coordinating.
        # The config for these is passed in from the ChiefOfStaff during setup.
        synthesizer_config = specialist_config.get("response_synthesizer_specialist", {})
        archiver_config = specialist_config.get("archiver_specialist", {})

        # Instantiate the specialists this coordinator will use.
        self.synthesizer = ResponseSynthesizerSpecialist("response_synthesizer_specialist", synthesizer_config)
        self.archiver = ArchiverSpecialist("archiver_specialist", archiver_config)

        # The coordinator is responsible for creating the LLM adapters for the specialists it owns.
        synthesizer_binding_key = synthesizer_config.get("llm_config")
        if synthesizer_binding_key:
            prompt_file = synthesizer_config.get("prompt_file")
            system_prompt = load_prompt(prompt_file) if prompt_file else ""
            self.synthesizer.llm_adapter = adapter_factory.create_adapter(synthesizer_binding_key, system_prompt)
            logger.info("EndSpecialist successfully created LLM adapter for its internal ResponseSynthesizer.")

        logger.info("---INITIALIZED EndSpecialist Coordinator---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrates the final synthesis and archiving steps.
        """
        logger.info("--- EndSpecialist: Beginning final termination sequence. ---")

        # Create a mutable copy of the state to avoid side effects.
        current_state = state.copy()

        # If no explicit snippets were provided by specialists, we should synthesize
        # the final response from the last meaningful AI message in the history.
        scratchpad = current_state.get("scratchpad", {})
        if not scratchpad.get("user_response_snippets"):
            logger.info("EndSpecialist: No user_response_snippets found. Attempting to synthesize from last AI message.")
            messages = current_state.get("messages", [])
            # Find the last message from a non-orchestrator specialist.
            last_ai_message = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage) and msg.name not in ["router_specialist", "prompt_triage_specialist"]), None)
            if last_ai_message and last_ai_message.content:
                # Place the content into the snippets for the synthesizer to find.
                current_state.setdefault("scratchpad", {})["user_response_snippets"] = [last_ai_message.content]
                logger.info(f"Found content from '{last_ai_message.name}' to use for final synthesis.")

        # 1. Conditional Synthesis
        if not current_state.get("artifacts", {}).get("final_user_response.md"):
            logger.info("EndSpecialist: Synthesizing final response.")
            synthesis_updates = self.synthesizer._execute_logic(current_state)
            # Perform a deep merge of the synthesis updates into the state for the archiver.
            current_state["messages"] = current_state.get("messages", []) + synthesis_updates.get("messages", [])
            current_state.setdefault("artifacts", {}).update(synthesis_updates.get("artifacts", {}))
            current_state.setdefault("scratchpad", {}).update(synthesis_updates.get("scratchpad", {}))
        else:
            logger.info("EndSpecialist: Final response already exists. Skipping synthesis.")

        # 2. Guaranteed Archiving
        logger.info("EndSpecialist: Archiving interaction.")
        archival_updates = self.archiver._execute_logic(current_state)

        # The archiver's updates are the final state changes.
        return archival_updates