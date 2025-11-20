# app/src/specialists/tiered_synthesizer_specialist.py
"""
TieredSynthesizerSpecialist - Combines multiple perspectives into a unified response.

This procedural specialist acts as the "join" node in the fan-out/join pattern
introduced by CORE-CHAT-002. It waits for both ProgenitorAlpha and ProgenitorBravo
to complete, then combines their responses into a formatted, tiered markdown output.

This is a PROCEDURAL specialist - it does NOT use an LLM.
"""
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from .helpers import create_llm_message

logger = logging.getLogger(__name__)


class TieredSynthesizerSpecialist(BaseSpecialist):
    """
    Combines multiple progenitor perspectives into a single, formatted response.

    This specialist procedurally merges the Alpha and Bravo perspectives into
    a tiered markdown document that presents both viewpoints to the user.
    It serves as the join node after parallel execution of the progenitors.

    Part of the Tiered Chat Subgraph (CORE-CHAT-002).
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initializes the TieredSynthesizerSpecialist.

        Args:
            specialist_name: The name of this specialist instance (must match config.yaml key)
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name} (Tiered Synthesizer)---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combines Alpha and Bravo perspectives into a formatted tiered response.

        This method retrieves both progenitor responses from artifacts, formats them
        as a multi-perspective markdown document, and prepares the final output for
        the user.

        Args:
            state: The current workflow state containing artifacts with progenitor responses

        Returns:
            Dictionary containing:
            - messages: AI message indicating synthesis completion
            - scratchpad: user_response_snippets with the combined tiered response
            - task_is_complete: True (signals workflow completion)

        Raises:
            ValueError: If either progenitor response is missing from artifacts
        """
        logger.info(f"--- {self.specialist_name}: Synthesizing tiered response. ---")

        artifacts = state.get("artifacts", {})

        # Retrieve both progenitor responses
        alpha_response = artifacts.get("alpha_response")
        bravo_response = artifacts.get("bravo_response")

        # CORE-CHAT-002.1: Graceful degradation for partial failures
        if not alpha_response and not bravo_response:
            logger.error(f"{self.specialist_name}: Both progenitor responses missing.")
            raise ValueError("TieredSynthesizerSpecialist requires at least one progenitor response")

        # Determine response mode for observability
        if alpha_response and bravo_response:
            response_mode = "tiered_full"
            tiered_response = self._format_tiered_response(alpha_response, bravo_response)
            logger.info(f"{self.specialist_name}: Full tiered response synthesized successfully.")
            status_msg = f"Combined {len(alpha_response)} chars from Alpha and {len(bravo_response)} chars from Bravo."
        elif alpha_response:
            response_mode = "tiered_alpha_only"
            tiered_response = self._format_single_perspective("Analytical View", alpha_response)
            logger.warning(f"{self.specialist_name}: Bravo perspective missing - using only Alpha (degraded mode).")
            status_msg = f"Single-perspective response from Alpha ({len(alpha_response)} chars). Bravo failed."
        else:  # only bravo_response
            response_mode = "tiered_bravo_only"
            tiered_response = self._format_single_perspective("Contextual View", bravo_response)
            logger.warning(f"{self.specialist_name}: Alpha perspective missing - using only Bravo (degraded mode).")
            status_msg = f"Single-perspective response from Bravo ({len(bravo_response)} chars). Alpha failed."

        # Create a message for the graph
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,  # Will be None for procedural specialists
            content=status_msg,
        )

        # Return the synthesized response in artifacts AND scratchpad
        # Writing to artifacts.final_user_response.md prevents EndSpecialist from
        # doing a redundant LLM synthesis call (CORE-CHAT-002 optimization)
        return {
            "messages": [ai_message],
            "artifacts": {
                "response_mode": response_mode,  # For observability in Archive Report
                "final_user_response.md": tiered_response  # Skip EndSpecialist synthesis
            },
            "scratchpad": {
                "user_response_snippets": [tiered_response]  # Kept for compatibility
            },
            "task_is_complete": True  # Signal that this workflow branch is complete
        }

    def _format_tiered_response(self, alpha_response: str, bravo_response: str) -> str:
        """
        Formats two perspectives into a structured markdown document.

        Args:
            alpha_response: The analytical perspective response
            bravo_response: The intuitive perspective response

        Returns:
            Formatted markdown string with both perspectives clearly delineated
        """
        formatted_response = f"""# Multi-Perspective Response

### Perspective 1: Analytical View

{alpha_response}

---

### Perspective 2: Contextual View

{bravo_response}

---

*This response combines multiple perspectives to provide a comprehensive answer.*
"""
        return formatted_response

    def _format_single_perspective(self, perspective_name: str, response: str) -> str:
        """
        Formats a single perspective response when the other perspective failed.

        This method is used for graceful degradation (CORE-CHAT-002.1) when one
        progenitor specialist fails but the other succeeds.

        Args:
            perspective_name: The name of the perspective (e.g., "Analytical View")
            response: The response text from the successful progenitor

        Returns:
            Formatted markdown string with the single perspective and a notice
        """
        formatted_response = f"""# Single-Perspective Response

### {perspective_name}

{response}

---

*Note: This response provides a single perspective due to a temporary issue with the multi-perspective system. The quality of the response is unaffected.*
"""
        return formatted_response
