# app/src/specialists/progenitor_bravo_specialist.py
"""
ProgenitorBravoSpecialist - Second perspective in the Tiered Chat Subgraph.

This specialist represents the "Bravo" perspective in the Diplomatic Process
(CORE-CHAT-002). It runs in parallel with ProgenitorAlphaSpecialist to provide
multiple perspectives on user queries. Its response is stored in artifacts for
combination by TieredSynthesizerSpecialist.

Part of the fan-out/join pattern for multi-perspective chat responses.
"""
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)


class ProgenitorBravoSpecialist(BaseSpecialist):
    """
    Provides the "Bravo" perspective in tiered chat responses.

    This specialist participates in parallel execution with ProgenitorAlphaSpecialist.
    Both perspectives are later combined by TieredSynthesizerSpecialist to create
    a multi-perspective response for the user.

    Represents the second "Tribal Territory" in the Diplomatic Process.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initializes the ProgenitorBravoSpecialist.

        Args:
            specialist_name: The name of this specialist instance (must match config.yaml key)
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name} (Bravo Progenitor)---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates the Bravo perspective response for the user's query.

        This method processes the full conversation history and generates a response
        from the Bravo perspective. The response is stored in artifacts for later
        combination with the Alpha perspective.

        Args:
            state: The current workflow state containing messages and other data

        Returns:
            Dictionary containing:
            - artifacts: Contains 'bravo_response' with the generated text

        CRITICAL STATE MANAGEMENT:
        - Does NOT append to 'messages' - only TieredSynthesizerSpecialist does
        - This follows the LangGraph pattern for parallel execution (fan-out/join)
        - Parallel nodes write to temporary storage (artifacts), join nodes write to permanent storage (messages)

        Note: Does NOT set task_is_complete - that's the TieredSynthesizer's role
        """
        logger.info(f"--- {self.specialist_name}: Generating Bravo perspective. ---")

        # Get messages with gathered_context injected (if Facilitator gathered any)
        messages = self._get_enriched_messages(state)

        # Check for uploaded image
        image_data = state.get("artifacts", {}).get("uploaded_image.png")

        # Create a standardized request with the full conversation history
        request = StandardizedLLMRequest(
            messages=messages,
            image_data=image_data
        )

        # Invoke the LLM adapter
        response_data = self.llm_adapter.invoke(request)

        # Extract the text response with fallback for None or missing values
        ai_response_content = response_data.get("text_response") or \
            "I apologize, but I'm unable to provide a response at this time."

        # Create a standardized AI message with LLM metadata
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=ai_response_content,
        )

        logger.info(f"{self.specialist_name}: Bravo perspective stored in artifacts (state management pattern for parallel execution).")

        # STATE MANAGEMENT PATTERN FOR PARALLEL EXECUTION:
        # - Progenitors (parallel nodes) write ONLY to 'artifacts' (temporary storage)
        # - TieredSynthesizer (join node) reads artifacts and writes to 'messages' (permanent storage)
        # - This prevents message pollution and enables proper multi-turn cross-referencing
        # NOTE: Using .md extension for proper archival (archiver needs extension to determine content type)
        return {
            "artifacts": {
                "bravo_response.md": ai_response_content
            }
            # NOTE: task_is_complete is NOT set - TieredSynthesizerSpecialist will set it
        }
