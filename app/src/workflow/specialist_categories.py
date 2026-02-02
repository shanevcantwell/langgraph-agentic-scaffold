"""
Single source of truth for specialist categorization.

This module centralizes the logic for categorizing specialists for:
- Graph node inclusion/exclusion
- Router tool schema exclusions
- Hub-and-spoke edge wiring exclusions

See ADR-CORE-028 for details.
"""
from typing import Set, List

from ..enums import CoreSpecialist


class SpecialistCategories:
    """
    Immutable categorization of specialists for routing and graph construction.

    Categories:
    - MCP_ONLY: Not added as graph nodes, accessed only via MCP
    - CORE_INFRASTRUCTURE: Router, archiver, end, critic - special graph roles
    - SERVICE_LAYER: MCP-only internal services (not user-facing)
    """

    # MCP-only: Not added as graph nodes, accessed only via MCP
    MCP_ONLY: frozenset = frozenset([
        "summarizer_specialist",
    ])

    # Core infrastructure: Special graph roles
    # ADR-ROADMAP-001: EXIT_INTERVIEW added - has special edge wiring (after_exit_interview)
    CORE_INFRASTRUCTURE: frozenset = frozenset([
        CoreSpecialist.ROUTER.value,
        CoreSpecialist.ARCHIVER.value,
        CoreSpecialist.END.value,
        CoreSpecialist.CRITIC.value,
        CoreSpecialist.EXIT_INTERVIEW.value,
    ])

    # Service layer: MCP-only internal services
    # NOTE: file_specialist removed - superseded by external filesystem MCP container (ADR-CORE-035)
    SERVICE_LAYER: frozenset = frozenset([])

    # ADR-CORE-053: Triage infrastructure - always excluded from triage menus
    # These are core infrastructure specialists that should never appear in triage's recommendations
    # ADR-ROADMAP-001: EXIT_INTERVIEW added - internal gate, not user-routable
    TRIAGE_INFRASTRUCTURE: frozenset = frozenset([
        CoreSpecialist.ROUTER.value,
        CoreSpecialist.ARCHIVER.value,
        CoreSpecialist.END.value,
        CoreSpecialist.CRITIC.value,
        CoreSpecialist.EXIT_INTERVIEW.value,
    ])

    @classmethod
    def get_router_exclusions(
        cls,
        subgraph_exclusions: List[str] = None,
        config_exclusions: List[str] = None
    ) -> Set[str]:
        """
        Returns specialists that should NOT appear in router's tool schema.

        Combines:
        - MCP-only specialists (not graph nodes)
        - Service layer specialists (internal services)
        - Subgraph-managed specialists (from subgraph.get_router_excluded_specialists())
        - Config-driven exclusions (from specialist.excluded_from lists) - Issue #90
        - Router itself (cannot route to itself)
        """
        exclusions = set(cls.MCP_ONLY) | set(cls.SERVICE_LAYER) | {CoreSpecialist.ROUTER.value}
        if subgraph_exclusions:
            exclusions.update(subgraph_exclusions)
        if config_exclusions:
            exclusions.update(config_exclusions)
        return exclusions

    @classmethod
    def get_hub_spoke_exclusions(cls, subgraph_exclusions: List[str] = None) -> Set[str]:
        """
        Returns specialists excluded from standard hub-and-spoke edge wiring.

        These specialists either:
        - Have special routing handled elsewhere (CORE_INFRASTRUCTURE)
        - Are not graph nodes (MCP_ONLY)
        - Are wired by their subgraph (subgraph_exclusions)
        """
        exclusions = set(cls.CORE_INFRASTRUCTURE) | set(cls.MCP_ONLY)
        if subgraph_exclusions:
            exclusions.update(subgraph_exclusions)
        return exclusions

    @classmethod
    def get_node_exclusions(cls) -> Set[str]:
        """
        Returns specialists that should NOT be added as graph nodes.
        """
        return set(cls.MCP_ONLY)

    @classmethod
    def get_triage_exclusions(
        cls,
        subgraph_exclusions: List[str] = None,
        config_exclusions: List[str] = None,
        current_triage_name: str = None
    ) -> Set[str]:
        """
        ADR-CORE-053: Returns specialists that should NOT appear in triage's menu.

        Combines:
        - TRIAGE_INFRASTRUCTURE (router, archiver, end, critic)
        - Subgraph-managed specialists (from subgraph.get_triage_excluded_specialists())
        - Config-driven exclusions (from specialist.excluded_from lists)
        - Current triage itself (cannot recommend itself)
        """
        exclusions = set(cls.TRIAGE_INFRASTRUCTURE)
        if subgraph_exclusions:
            exclusions.update(subgraph_exclusions)
        if config_exclusions:
            exclusions.update(config_exclusions)
        if current_triage_name:
            exclusions.add(current_triage_name)
        return exclusions
