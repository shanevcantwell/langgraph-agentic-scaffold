"""
Distillation Prompt Aggregator Specialist

This specialist aggregates expanded prompts from parallel expander invocations.
It follows the synthesizer pattern: reads from artifacts, aggregates, and promotes
to distillation_state for persistence.

Reference: docs/ADR/DISTILLATION_IMPLEMENTATION_PLAN.md Phase 1.3
"""

import logging
from typing import Dict, Any, List

from .base import BaseSpecialist

logger = logging.getLogger(__name__)


class DistillationPromptAggregatorSpecialist(BaseSpecialist):
    """
    Aggregates expanded prompt variations from expander specialist(s).

    Workflow Pattern: Synthesizer (Fan-in Join)
    - Reads from artifacts.expanded_prompts_batch (written by expanders)
    - Aggregates and deduplicates variations
    - Promotes to distillation_state.expanded_prompts
    - Increments distillation_state.expansion_index
    - Writes to messages for permanent history

    This is a PROCEDURAL specialist (no LLM required).
    Type in config.yaml: "procedural"
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initialize the DistillationPromptAggregatorSpecialist.

        Args:
            specialist_name: The name of this specialist instance
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name} (PROCEDURAL)---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregate expanded prompts from artifacts into distillation_state.

        Args:
            state: GraphState containing artifacts and distillation_state

        Returns:
            Dict updating distillation_state with aggregated prompts

        Raises:
            KeyError: If required state fields missing
        """
        logger.info(f"--- {self.specialist_name}: Aggregating expanded prompts ---")

        # Extract state fields
        artifacts = state.get("artifacts", {})
        distillation_state = state.get("distillation_state", {})

        if not distillation_state:
            raise KeyError("distillation_state not found in GraphState")

        # Read expanded prompts from artifacts (written by expander)
        expanded_batch = artifacts.get("expanded_prompts_batch", [])

        if not expanded_batch:
            logger.warning("No expanded_prompts_batch found in artifacts - batch was empty")
            expanded_batch = []

        # Get existing expanded prompts (may be from previous aggregations)
        existing_expanded = distillation_state.get("expanded_prompts", [])

        # Aggregate and deduplicate
        aggregated = self._aggregate_and_deduplicate(
            existing=existing_expanded,
            new_batch=expanded_batch
        )

        # Increment expansion index
        expansion_index = distillation_state.get("expansion_index", 0)
        next_expansion_index = expansion_index + 1
        seeds_processed = distillation_state.get("seeds_processed", 0) + 1

        logger.info(
            f"Aggregated {len(expanded_batch)} new variations. "
            f"Total expanded prompts: {len(aggregated)}. "
            f"Next expansion_index: {next_expansion_index}"
        )

        # Return updated distillation_state
        return {
            "distillation_state": {
                "expanded_prompts": aggregated,
                "expansion_index": next_expansion_index,
                "seeds_processed": seeds_processed,
            }
        }

    def _aggregate_and_deduplicate(
        self,
        existing: List[str],
        new_batch: List[str]
    ) -> List[str]:
        """
        Aggregate new variations with existing, removing duplicates.

        Args:
            existing: Previously aggregated variations
            new_batch: New variations from current expander invocation

        Returns:
            Combined list with duplicates removed (preserves order)
        """
        # Use dict to preserve order while deduplicating
        # (Python 3.7+ dicts maintain insertion order)
        seen = {}

        # Add existing variations first
        for prompt in existing:
            normalized = prompt.strip().lower()
            if normalized and normalized not in seen:
                seen[normalized] = prompt

        # Add new variations
        duplicates_found = 0
        for prompt in new_batch:
            normalized = prompt.strip().lower()
            if not normalized:
                continue  # Skip empty strings

            if normalized in seen:
                duplicates_found += 1
            else:
                seen[normalized] = prompt

        if duplicates_found > 0:
            logger.info(f"Removed {duplicates_found} duplicate variations during aggregation")

        # Return original (non-normalized) prompts in order
        return list(seen.values())
