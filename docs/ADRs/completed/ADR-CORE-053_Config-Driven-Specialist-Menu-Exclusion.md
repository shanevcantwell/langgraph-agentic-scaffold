# ADR-CORE-053: Config-Driven Specialist Menu Exclusion

**Status:** Proposed
**Date:** 2026-01-25
**Closes:** Issue #63
**Relates To:** ADR-CORE-028 (Centralized Specialist Exclusion Logic), ADR-CORE-016 (Menu Filter Pattern)

---

## Context

Triage's specialist menu is controlled by a hardcoded list in `graph_builder.py:574`:

```python
excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value,
            CoreSpecialist.ARCHIVER.value, CoreSpecialist.END.value,
            CoreSpecialist.CRITIC.value, "triage_architect"]
```

This requires code changes to adjust specialist visibility. Several specialists are missing from exclusions:
- `progenitor_alpha_specialist`, `progenitor_bravo_specialist` (internal subgraph nodes)
- `tiered_synthesizer_specialist` (internal subgraph node)
- `batch_processor_specialist` (internal execution engine)
- `facilitator_specialist`, `dialogue_specialist` (context engineering chain)

ADR-CORE-028 established `SpecialistCategories` as the single source of truth for exclusion logic, but it has no `get_triage_exclusions()` method. The triage exclusion list remains hardcoded independently.

---

## Decision

Add `excluded_from: List[str]` property to specialist config (following the existing `tags` pattern). Build an inverted index at graph construction time. Any specialist that builds a menu can query the index.

### Schema Change

```python
# app/src/utils/config_schema.py - BaseSpecialistConfig

excluded_from: Optional[List[str]] = Field(
    default=None,
    description="List of specialist names whose menus should NOT include this specialist."
)
```

### Config Usage

```yaml
batch_processor_specialist:
  type: "llm"
  prompt_file: "batch_processor_prompt.md"
  description: "Internal execution engine..."
  excluded_from: ["triage_architect", "prompt_triage_specialist"]

progenitor_alpha_specialist:
  type: "llm"
  prompt_file: "progenitor_alpha_prompt.md"
  description: "First perspective in tiered chat..."
  excluded_from: ["triage_architect"]
```

### Inverted Index

GraphBuilder builds an inverted index at construction time:

```python
def _build_exclusion_index(self, configs: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Build inverted index: excluder -> set of excluded specialists."""
    index: Dict[str, Set[str]] = defaultdict(set)
    for name, conf in configs.items():
        for excluder in conf.get("excluded_from", []):
            index[excluder].add(name)
    return index
```

Result: `{"triage_architect": {"batch_processor", "progenitor_alpha", ...}}`

### Consumption

```python
# In _configure_triage()
config_exclusions = self.exclusion_index.get(specialist_name, set())
```

---

## Exclusion Taxonomy

This ADR completes a trilogy of exclusion mechanisms:

| Pattern | When | Who Decides | Mechanism |
|---------|------|-------------|-----------|
| `excluded_from` (ADR-053) | Config-time | Config author | Baked into specialist_map at build |
| `forbidden_specialists` (ADR-016) | Runtime (loop) | InvariantMonitor | Checked per-turn via scratchpad |
| `decline_task` (ADR-016) | Runtime (self) | Specialist | Removed from recommendations |

All three are conceptually "don't show specialist X in menu Y" but operate at different lifecycle stages.

---

## Implementation

### Files to Modify

| File | Change |
|------|--------|
| `config_schema.py` | Add `excluded_from: Optional[List[str]]` to BaseSpecialistConfig |
| `specialist_categories.py` | Add `TRIAGE_INFRASTRUCTURE` frozenset + `get_triage_exclusions()` method |
| `base_subgraph.py` | Add `get_triage_excluded_specialists()` interface method |
| `graph_builder.py` | Add `_build_exclusion_index()`, update `_configure_triage()` |
| `config.yaml` | Add `excluded_from` lists to relevant specialists |

### SpecialistCategories Extension

```python
TRIAGE_INFRASTRUCTURE: frozenset = frozenset([
    CoreSpecialist.ROUTER.value,
    CoreSpecialist.ARCHIVER.value,
    CoreSpecialist.END.value,
    CoreSpecialist.CRITIC.value,
])

@classmethod
def get_triage_exclusions(
    cls,
    subgraph_exclusions: List[str] = None,
    config_exclusions: List[str] = None,
    current_triage_name: str = None
) -> Set[str]:
    exclusions = set(cls.TRIAGE_INFRASTRUCTURE)
    if subgraph_exclusions:
        exclusions.update(subgraph_exclusions)
    if config_exclusions:
        exclusions.update(config_exclusions)
    if current_triage_name:
        exclusions.add(current_triage_name)
    return exclusions
```

---

## Consequences

### Positive

1. **Config-driven:** Adjust specialist visibility without code changes
2. **Schema-first:** `excluded_from` follows existing `tags` pattern
3. **Extensible:** New menu-building specialists just query the index
4. **Centralized:** Aligns with ADR-CORE-028's single-source-of-truth principle

### Negative

1. **Indirection:** One more config field to understand
2. **Inverted index:** Mental model requires understanding the inversion

### Neutral

1. **Subgraphs still declare exclusions:** `get_triage_excluded_specialists()` provides programmatic exclusions for internal nodes

---

## Future Extensibility

When adding a new menu-building specialist (e.g., `plan_specialist`):

1. Add `plan_specialist` to `excluded_from` lists in config.yaml
2. In configuration code: `self.exclusion_index.get("plan_specialist", set())`

**No code changes needed** - just config.yaml updates.

---

## References

- **ADR-CORE-028:** Centralized Specialist Exclusion Logic (pattern to follow)
- **ADR-CORE-016:** Menu Filter Pattern (runtime exclusion via `forbidden_specialists`)
- **Issue #63:** Feature request for `triage_excluded` config flag
- `app/src/utils/config_schema.py` - BaseSpecialistConfig with `tags` pattern
- `app/src/workflow/specialist_categories.py` - Existing exclusion categories
