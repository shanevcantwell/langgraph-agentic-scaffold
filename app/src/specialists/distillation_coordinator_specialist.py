"""
Distillation Coordinator Specialist

This specialist orchestrates the multi-phase distillation workflow across domains.
It manages state transitions, domain iteration, and phase progressions without making LLM calls.

Reference: docs/ADR/ADR-DISTILL-005_Multi_Phase_Coordinator.md
"""

import logging
import time
from typing import Dict, Any, List
from enum import Enum
from pathlib import Path

from .base import BaseSpecialist
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class DistillationPhase(Enum):
    """Workflow phases managed by coordinator."""
    EXPANSION = "expansion"
    RESPONSE_COLLECTION = "response_collection"
    PERSISTENCE = "persistence"


class DistillationCoordinatorSpecialist(BaseSpecialist):
    """
    Orchestrates federated distillation workflow across multiple phases and domains.

    Responsibilities:
    - Initialize workflow state on first call
    - Load seed prompts for each domain
    - Manage phase transitions (expansion → response_collection → persistence)
    - Track domain iteration
    - Handle workflow completion

    This is a PROCEDURAL specialist (no LLM required).
    Type in config.yaml: "procedural"

    State Machine:
    1. EXPANSION: Generate prompt variations from seeds
    2. RESPONSE_COLLECTION: Collect teacher model responses
    3. PERSISTENCE: Finalize domain dataset, move to next domain

    Configuration (from config.yaml):
    - domains: List of domain names to process
    - seeds_per_domain: Number of seed prompts to load per domain (default: 10)
    - variations_per_seed: Variations to generate per seed (default: 3)
    - output_dir: Root directory for datasets (default: ./datasets)
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initialize the DistillationCoordinatorSpecialist.

        Args:
            specialist_name: The name of this specialist instance
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)

        # Extract configuration
        self.domains = specialist_config.get("domains", [])
        self.seeds_per_domain = specialist_config.get("seeds_per_domain", 10)
        self.variations_per_seed = specialist_config.get("variations_per_seed", 3)
        self.output_dir = specialist_config.get("output_dir", "./datasets")

        # Workflow tracking
        self.workflow_start_time = None

        logger.info(
            f"---INITIALIZED {self.specialist_name} (PROCEDURAL)--- "
            f"{len(self.domains)} domains, {self.seeds_per_domain} seeds/domain"
        )

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main coordinator logic: routes to appropriate handler based on workflow state.

        Args:
            state: GraphState

        Returns:
            Dict with distillation_state updates and routing signals
        """
        dist_state = state.get("distillation_state")

        # First call: initialize workflow
        if not dist_state or not dist_state.get("current_phase"):
            return self._initialize_workflow(state)

        # Route based on current phase
        current_phase = dist_state.get("current_phase")

        if current_phase == DistillationPhase.EXPANSION.value:
            return self._handle_expansion_phase(state)
        elif current_phase == DistillationPhase.RESPONSE_COLLECTION.value:
            return self._handle_response_collection_phase(state)
        elif current_phase == DistillationPhase.PERSISTENCE.value:
            return self._handle_persistence_phase(state)
        else:
            raise ValueError(f"Unknown phase: {current_phase}")

    def _initialize_workflow(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize distillation workflow on first coordinator call.

        Returns:
            State update with initialized distillation_state + route to first expander
        """
        logger.info("=== Initializing Distillation Workflow ===")

        self.workflow_start_time = time.time()

        # Validate configuration
        if not self.domains:
            raise ValueError("No domains configured for distillation")

        # Start with first domain
        first_domain = self.domains[0]
        logger.info(f"Loading domain: {first_domain}")

        # Load seed prompts for first domain
        seed_prompts = self._load_seeds(first_domain)

        logger.info(
            f"Loaded {len(seed_prompts)} seeds from domain '{first_domain}'. "
            f"Starting EXPANSION phase."
        )

        # Initialize distillation_state
        return {
            "distillation_state": {
                "domains": self.domains,
                "current_domain": first_domain,
                "domain_index": 0,
                "seed_prompts": seed_prompts,
                "expanded_prompts": [],
                "expansion_index": 0,
                "collection_index": 0,
                "seeds_processed": 0,
                "responses_collected": 0,
                "error_count": 0,
                "current_phase": DistillationPhase.EXPANSION.value,
                "temp_dataset_path": None,
                "completed_dataset_paths": [],
                "variations_per_seed": self.variations_per_seed,
                "output_dir": self.output_dir,
            },
            "scratchpad": {
                "next_specialist": "distillation_prompt_expander_specialist"
            }
        }

    def _handle_expansion_phase(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle expansion phase: check if more seeds to expand or transition to collection.

        Args:
            state: GraphState with distillation_state

        Returns:
            State update with routing signal
        """
        dist_state = state.get("distillation_state", {})

        seed_prompts = dist_state.get("seed_prompts", [])
        expansion_index = dist_state.get("expansion_index", 0)

        if expansion_index < len(seed_prompts):
            # More seeds to expand - route to expander
            logger.info(
                f"EXPANSION phase: {expansion_index}/{len(seed_prompts)} seeds processed. "
                f"Routing to expander."
            )
            return {
                "scratchpad": {
                    "next_specialist": "distillation_prompt_expander_specialist"
                }
            }
        else:
            # All seeds expanded - transition to response collection
            logger.info(
                f"EXPANSION complete: {expansion_index} seeds expanded. "
                f"Transitioning to RESPONSE_COLLECTION phase."
            )
            return {
                "distillation_state": {
                    "current_phase": DistillationPhase.RESPONSE_COLLECTION.value,
                    "collection_index": 0,  # Reset for collection
                },
                "scratchpad": {
                    "next_specialist": "distillation_response_collector_specialist"
                }
            }

    def _handle_response_collection_phase(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle response collection phase: check if more prompts to collect or transition to persistence.

        Args:
            state: GraphState with distillation_state

        Returns:
            State update with routing signal
        """
        dist_state = state.get("distillation_state", {})

        expanded_prompts = dist_state.get("expanded_prompts", [])
        collection_index = dist_state.get("collection_index", 0)

        if collection_index < len(expanded_prompts):
            # More prompts to collect - route to collector
            logger.info(
                f"RESPONSE_COLLECTION phase: {collection_index}/{len(expanded_prompts)} "
                f"prompts processed. Routing to collector."
            )
            return {
                "scratchpad": {
                    "next_specialist": "distillation_response_collector_specialist"
                }
            }
        else:
            # All prompts collected - transition to persistence
            logger.info(
                f"RESPONSE_COLLECTION complete: {collection_index} responses collected. "
                f"Transitioning to PERSISTENCE phase."
            )
            return {
                "distillation_state": {
                    "current_phase": DistillationPhase.PERSISTENCE.value,
                },
                "scratchpad": {
                    "next_specialist": "distillation_coordinator_specialist"  # Self
                }
            }

    def _handle_persistence_phase(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle persistence phase: finalize domain dataset and move to next domain or complete.

        Args:
            state: GraphState with distillation_state

        Returns:
            State update with routing signal or completion
        """
        dist_state = state.get("distillation_state", {})

        current_domain = dist_state.get("current_domain")
        domain_index = dist_state.get("domain_index", 0)
        completed_paths = dist_state.get("completed_dataset_paths", [])

        logger.info(f"PERSISTENCE phase: Finalizing domain '{current_domain}'")

        # Finalize domain dataset (placeholder - actual persistence is already done by collector)
        # In future: could rename temp files, write metadata, etc.
        domain_dataset_path = f"{self.output_dir}/{current_domain}/"
        completed_paths.append(domain_dataset_path)

        # Check if more domains to process
        next_domain_index = domain_index + 1

        if next_domain_index < len(self.domains):
            # Move to next domain
            next_domain = self.domains[next_domain_index]
            logger.info(
                f"Domain '{current_domain}' complete. "
                f"Moving to next domain: '{next_domain}' ({next_domain_index + 1}/{len(self.domains)})"
            )

            # Load seeds for next domain
            seed_prompts = self._load_seeds(next_domain)

            return {
                "distillation_state": {
                    "current_domain": next_domain,
                    "domain_index": next_domain_index,
                    "seed_prompts": seed_prompts,
                    "expanded_prompts": [],  # Reset for new domain
                    "expansion_index": 0,
                    "collection_index": 0,
                    "seeds_processed": 0,  # Reset for new domain
                    "responses_collected": 0,  # Reset for new domain
                    "error_count": 0,  # Reset for new domain
                    "current_phase": DistillationPhase.EXPANSION.value,
                    "completed_dataset_paths": completed_paths,
                },
                "scratchpad": {
                    "next_specialist": "distillation_prompt_expander_specialist"
                }
            }
        else:
            # All domains complete - workflow done
            duration = time.time() - (self.workflow_start_time or time.time())
            logger.info(
                f"=== Distillation Workflow COMPLETE === "
                f"Processed {len(self.domains)} domains in {duration/3600:.2f} hours"
            )

            return {
                "distillation_state": {
                    "current_phase": "complete",
                    "completed_dataset_paths": completed_paths,
                },
                "task_is_complete": True
            }

    def _load_seeds(self, domain: str) -> List[str]:
        """
        Load seed prompts for a domain from markdown file.

        Args:
            domain: Domain name (e.g., "agentic_architecture")

        Returns:
            List of seed prompt strings

        Raises:
            FileNotFoundError: If domain seed file not found
        """
        # Load from app/prompts/distillation_seeds/{domain}.md
        try:
            seed_file_content = load_prompt(f"distillation_seeds/{domain}.md")

            # Parse markdown file to extract seed prompts
            # Seeds are numbered list items (1., 2., etc.)
            seeds = []
            for line in seed_file_content.split('\n'):
                line = line.strip()
                # Match numbered list items: "1. Seed prompt text..."
                if line and line[0].isdigit() and '. ' in line:
                    # Extract text after "N. "
                    seed_text = line.split('. ', 1)[1]
                    seeds.append(seed_text)

                    # Limit to seeds_per_domain
                    if len(seeds) >= self.seeds_per_domain:
                        break

            if not seeds:
                logger.warning(f"No seeds found in {domain}.md. Using placeholder seed.")
                seeds = [f"Explain key concepts in {domain}."]

            logger.info(f"Loaded {len(seeds)} seeds for domain '{domain}'")
            return seeds

        except FileNotFoundError:
            logger.error(f"Seed file not found for domain '{domain}'")
            raise
