# ADR-CORE-028: Centralized Specialist Exclusion Logic

**Status:** IMPLEMENTED
**Date:** 2025-12-18
**Implements:** GraphBuilder Refactoring for Maintainable Exclusion Logic
**Related ADRs:** ADR-CORE-008 (MCP Architecture), ADR-CORE-027 (Navigation-MCP Integration)

---

## Context

The GraphBuilder had multiple locations where specialist exclusion logic was defined:

1. **Node creation** - Which specialists become graph nodes
2. **Router tool schema** - Which specialists appear in router's LLM prompt
3. **Hub-and-spoke wiring** - Which specialists get standard router edges
4. **Dynamic filtering** - Runtime exclusions (e.g., context_engineering specialists after context gathered)

This duplication created several problems:

```python
# Problem: Scattered exclusion logic
class GraphBuilder:
    def _add_nodes(self):
        # Exclusion logic here
        mcp_only = ["summarizer_specialist", "file_specialist"]
        ...

    def _configure_router(self):
        # Different exclusion logic here
        excluded = [CoreSpecialist.ROUTER.value] + mcp_only_specialists
        ...

    def _wire_hub_and_spoke(self):
        # Yet another exclusion list
        excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.ARCHIVER.value, ...]
```

**Consequences:**
- Adding a new MCP-only specialist required changes in 3+ locations
- Risk of inconsistency between exclusion sets
- Difficult to reason about which specialists appear where
- Tag-based dynamic filtering duplicated in RouterSpecialist

---

## Decision

We introduce **SpecialistCategories** as the single source of truth for specialist categorization, centralizing all exclusion logic in one module.

### SpecialistCategories Class

```python
# app/src/workflow/specialist_categories.py
class SpecialistCategories:
    """
    Immutable categorization of specialists for routing and graph construction.
    """

    # MCP-only: Not added as graph nodes, accessed only via MCP
    MCP_ONLY: frozenset = frozenset([
        "summarizer_specialist",
    ])

    # Core infrastructure: Special graph roles
    CORE_INFRASTRUCTURE: frozenset = frozenset([
        CoreSpecialist.ROUTER.value,
        CoreSpecialist.ARCHIVER.value,
        CoreSpecialist.END.value,
        CoreSpecialist.CRITIC.value,
    ])

    # Service layer: MCP-only internal services
    SERVICE_LAYER: frozenset = frozenset([
        "file_specialist",  # MCP-only service, use file_operations_specialist for user requests
    ])

    @classmethod
    def get_router_exclusions(cls, subgraph_exclusions: List[str] = None) -> Set[str]:
        """Specialists excluded from router's tool schema."""
        exclusions = set(cls.MCP_ONLY) | set(cls.SERVICE_LAYER) | {CoreSpecialist.ROUTER.value}
        if subgraph_exclusions:
            exclusions.update(subgraph_exclusions)
        return exclusions

    @classmethod
    def get_hub_spoke_exclusions(cls, subgraph_exclusions: List[str] = None) -> Set[str]:
        """Specialists excluded from standard hub-and-spoke edge wiring."""
        exclusions = set(cls.CORE_INFRASTRUCTURE) | set(cls.MCP_ONLY)
        if subgraph_exclusions:
            exclusions.update(subgraph_exclusions)
        return exclusions

    @classmethod
    def get_node_exclusions(cls) -> Set[str]:
        """Specialists not added as graph nodes."""
        return set(cls.MCP_ONLY)
```

### Categories Defined

| Category | Specialists | Graph Node? | In Router Menu? | Hub-Spoke Wiring? |
|----------|-------------|-------------|-----------------|-------------------|
| **MCP_ONLY** | summarizer_specialist | No | No | N/A |
| **SERVICE_LAYER** | file_specialist | Yes | No | Yes |
| **CORE_INFRASTRUCTURE** | router, archiver, end, critic | Yes | Varies | No (special wiring) |
| **Standard** | All others | Yes | Yes | Yes |

### GraphBuilder Integration

```python
# graph_builder.py - All exclusion calls now go through SpecialistCategories

def _add_nodes(self):
    node_exclusions = SpecialistCategories.get_node_exclusions()
    for name, instance in self.specialists.items():
        if name in node_exclusions:
            logger.info(f"Skipping node creation for MCP-only specialist: {name}")
            continue
        self.graph.add_node(name, instance.execute)

def _configure_router(self, router_instance, configs):
    excluded_from_router = SpecialistCategories.get_router_exclusions(subgraph_exclusions)
    available_specialists = {name: conf for name, conf in configs.items() if name not in excluded_from_router}
    router_instance.set_specialist_map(available_specialists)

def _wire_hub_and_spoke(self):
    excluded_specialists = SpecialistCategories.get_hub_spoke_exclusions(subgraph_exclusions)
    for name in self.specialists:
        if name in excluded_specialists:
            continue
        self.graph.add_edge(name, CoreSpecialist.ROUTER.value)
```

### Subgraph Integration

Subgraphs can provide their own exclusions that get merged:

```python
class ContextEngineeringSubgraph(BaseSubgraph):
    def get_router_excluded_specialists(self) -> List[str]:
        """Specialists managed by this subgraph, hidden from main router."""
        return [
            "triage_architect",
            "facilitator_specialist",
        ]

    def get_excluded_specialists(self) -> List[str]:
        """Specialists excluded from standard hub-and-spoke wiring."""
        return self.get_router_excluded_specialists()
```

### Dynamic Tag-Based Filtering

RouterSpecialist uses specialist tags for runtime filtering (complementary to static exclusions):

```python
# router_specialist.py
def _get_available_specialists(self, state: Dict[str, Any]) -> Dict[str, Dict]:
    all_specialists = self.specialist_map

    # After context gathering, remove context_engineering specialists
    if gathered_context:
        planning_specialists = [
            name for name, spec in all_specialists.items()
            if "context_engineering" in spec.get("tags", [])
        ]
        all_specialists = {name: spec for name, spec in all_specialists.items()
                          if name not in planning_specialists}
```

**Tag types:**
- `context_engineering` - Triage and facilitator specialists
- `planning` - Systems architect, planning specialists
- `vision_capable` - Specialists that can process images

---

## Consequences

### Positive

1. **Single source of truth** - All exclusion logic in one place
2. **Type safety** - `frozenset` prevents accidental modification
3. **Composable** - Subgraph exclusions merge cleanly
4. **Self-documenting** - Category names explain purpose
5. **Testable** - Categories can be unit tested independently
6. **Maintainable** - Adding new MCP-only specialist = 1 line change

### Negative

1. **Import dependency** - All graph components import SpecialistCategories
2. **Two-layer system** - Static categories + dynamic tag filtering
3. **Learning curve** - Developers must understand category vs tag distinction

### Static vs Dynamic Filtering

| Aspect | Static (SpecialistCategories) | Dynamic (Tag-based) |
|--------|-------------------------------|---------------------|
| **When** | Graph construction time | Runtime (per request) |
| **Purpose** | Structural exclusions | Contextual exclusions |
| **Examples** | MCP-only, service layer | Post-context-gathering filtering |
| **Location** | SpecialistCategories class | RouterSpecialist._get_available_specialists |
| **Immutable?** | Yes (frozenset) | No (filtered per request) |

---

## Migration Guide

### Adding a New MCP-Only Specialist

```python
# Before: Changes required in 3+ locations
# After: Single change in SpecialistCategories

class SpecialistCategories:
    MCP_ONLY: frozenset = frozenset([
        "summarizer_specialist",
        "my_new_mcp_specialist",  # Add here only
    ])
```

### Adding a New Infrastructure Specialist

```python
class SpecialistCategories:
    CORE_INFRASTRUCTURE: frozenset = frozenset([
        CoreSpecialist.ROUTER.value,
        CoreSpecialist.ARCHIVER.value,
        CoreSpecialist.END.value,
        CoreSpecialist.CRITIC.value,
        CoreSpecialist.MY_NEW_INFRA.value,  # Add here
    ])
```

### Adding a New Dynamic Tag

```python
# In specialist config (specialists.yaml)
my_specialist:
  description: "Does something"
  tags:
    - "my_custom_tag"

# In RouterSpecialist
def _get_available_specialists(self, state):
    if some_condition:
        tagged_specialists = [
            name for name, spec in all_specialists.items()
            if "my_custom_tag" in spec.get("tags", [])
        ]
        # Filter as needed
```

---

## References

- [app/src/workflow/specialist_categories.py](app/src/workflow/specialist_categories.py)
- [app/src/workflow/graph_builder.py](app/src/workflow/graph_builder.py)
- [app/src/specialists/router_specialist.py](app/src/specialists/router_specialist.py)
- Commit: c906348 (refactor(graph_builder): centralize specialist exclusion logic)
