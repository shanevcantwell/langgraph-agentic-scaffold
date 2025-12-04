import logging
from typing import Dict, Optional

from app.src.specialists.schemas._manifest import AgentAffinity

logger = logging.getLogger(__name__)

class AgentRouter:
    """
    Maps abstract AgentAffinity (from Manifest) to concrete Specialist IDs.
    Acts as the dispatch logic for the TribeConductor.
    """

    # Default mapping of Affinity -> Specialist ID
    # These IDs must match the keys used in the LangGraph builder
    _DEFAULT_MAPPING = {
        AgentAffinity.ARCHITECTURE: "progenitor_alpha_specialist",
        AgentAffinity.IMPLEMENTATION: "progenitor_bravo_specialist",
        AgentAffinity.RESEARCH: "project_director",  # Maps to ProjectDirector
        AgentAffinity.INFERENCE: "inference_specialist",  # Placeholder / Future
        AgentAffinity.MONITORING: "local_monitor",        # Placeholder / Future
        AgentAffinity.DEFAULT: "progenitor_bravo_specialist"
    }

    def __init__(self, custom_mapping: Optional[Dict[AgentAffinity, str]] = None):
        """
        Initialize the router with an optional custom mapping override.
        """
        self.mapping = self._DEFAULT_MAPPING.copy()
        if custom_mapping:
            self.mapping.update(custom_mapping)

    def route(self, affinity: AgentAffinity, prefer_fast: bool = False, prefer_cheap: bool = False) -> str:
        """
        Determine the best specialist ID for a given affinity.
        
        Args:
            affinity: The AgentAffinity from the branch pointer.
            prefer_fast: (Future) Hint to select a faster/smaller model variant.
            prefer_cheap: (Future) Hint to select a cheaper model variant.

        Returns:
            str: The specialist_id to route to.
        """
        # Fallback for unknown affinities
        if affinity not in self.mapping:
            logger.warning(f"AgentRouter: Unknown affinity '{affinity}', defaulting to {AgentAffinity.DEFAULT}")
            return self.mapping[AgentAffinity.DEFAULT]

        specialist_id = self.mapping[affinity]
        
        # TODO: Implement logic for prefer_fast/prefer_cheap when we have multiple
        # specialists for the same affinity (e.g., "research_fast" vs "research_deep")
        
        logger.debug(f"AgentRouter: Routing {affinity} -> {specialist_id}")
        return specialist_id

    def get_affinity_for_specialist(self, specialist_id: str) -> AgentAffinity:
        """
        Reverse lookup: Find the primary affinity for a given specialist ID.
        Useful for logging or default branch creation.
        """
        for affinity, mapped_id in self.mapping.items():
            if mapped_id == specialist_id:
                return affinity
        return AgentAffinity.DEFAULT
