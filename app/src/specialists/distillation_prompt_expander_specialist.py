"""
Distillation Prompt Expander Specialist

This specialist generates variations of seed prompts for model distillation training data.
It follows the progenitor pattern: takes ONE seed per invocation and writes variations
to artifacts for aggregation downstream.

Reference: docs/ADR/DISTILLATION_IMPLEMENTATION_PLAN.md Phase 1.2
"""

import logging
import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class DistillationPromptExpanderSpecialist(BaseSpecialist):
    """
    Expands a single seed prompt into multiple variations for distillation training.

    Workflow Pattern: Progenitor (Parallel Execution)
    - Takes ONE seed from distillation_state.seed_prompts[expansion_index]
    - Generates N variations via LLM
    - Writes to artifacts.expanded_prompts_batch (NOT messages)
    - Aggregator specialist later promotes to distillation_state

    Configuration:
    - variations_per_seed: Number of variations to generate (default: 3)
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initialize the DistillationPromptExpanderSpecialist.

        Args:
            specialist_name: The name of this specialist instance
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)

        # Load the expansion prompt template
        self.prompt_template = load_prompt("distillation_expander_prompt.md")
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expand a single seed prompt into variations.

        Args:
            state: GraphState containing distillation_state

        Returns:
            Dict with artifacts.expanded_prompts_batch containing variations

        Raises:
            KeyError: If distillation_state not properly initialized
            ValueError: If LLM returns invalid JSON
        """
        logger.info(f"--- {self.specialist_name}: Expanding seed prompt ---")

        # Extract distillation state
        distillation_state = state.get("distillation_state", {})
        if not distillation_state:
            raise KeyError("distillation_state not found in GraphState")

        # Get current seed to expand
        seed_prompts = distillation_state.get("seed_prompts", [])
        expansion_index = distillation_state.get("expansion_index", 0)
        current_domain = distillation_state.get("current_domain", "unknown")
        variations_per_seed = distillation_state.get("variations_per_seed", 3)

        if expansion_index >= len(seed_prompts):
            logger.error(
                f"expansion_index ({expansion_index}) exceeds seed_prompts length ({len(seed_prompts)})"
            )
            return {"error": "Expansion index out of range"}

        seed_prompt = seed_prompts[expansion_index]
        logger.info(
            f"Expanding seed {expansion_index + 1}/{len(seed_prompts)} "
            f"in domain '{current_domain}' ({len(seed_prompt)} chars)"
        )

        # Format prompt with seed and configuration
        formatted_prompt = self.prompt_template.format(
            domain=current_domain,
            seed_prompt=seed_prompt,
            variations_count=variations_per_seed
        )

        # Call LLM to generate variations
        try:
            variations = self._call_llm_for_variations(formatted_prompt)
            logger.info(f"Successfully generated {len(variations)} variations")

            # Return variations in artifacts (progenitor pattern)
            return {
                "artifacts": {
                    "expanded_prompts_batch": variations
                }
            }

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}", exc_info=True)
            # Return empty batch on failure - aggregator will handle empty batches
            return {
                "artifacts": {
                    "expanded_prompts_batch": []
                }
            }

    def _call_llm_for_variations(self, formatted_prompt: str) -> List[str]:
        """
        Call LLM to generate prompt variations.

        Args:
            formatted_prompt: The complete prompt with seed and instructions

        Returns:
            List of variation strings

        Raises:
            json.JSONDecodeError: If LLM response is not valid JSON
            ValueError: If JSON structure is invalid
        """
        # Create LLM request
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=formatted_prompt)]
        )

        # Invoke LLM
        response_data = self.llm_adapter.invoke(request)
        text_response = response_data.get("text_response", "")

        # Parse JSON response
        try:
            # Try direct parse first
            parsed = json.loads(text_response)
        except json.JSONDecodeError:
            # Fallback: extract JSON from markdown code blocks
            parsed = self._extract_json_from_text(text_response)

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object, got {type(parsed)}")

        variations = parsed.get("variations", [])
        if not isinstance(variations, list):
            raise ValueError(f"'variations' must be a list, got {type(variations)}")

        if not variations:
            logger.warning("LLM returned empty variations list")

        return variations

    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract JSON from text that may contain markdown code blocks.

        Args:
            text: Text potentially containing JSON

        Returns:
            Parsed JSON object

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        import re

        # Try to find JSON in markdown code blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # Try to find raw JSON object
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # No JSON found
        raise json.JSONDecodeError("No JSON object found in text", text, 0)
