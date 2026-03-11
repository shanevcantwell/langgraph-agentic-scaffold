# ADR-CORE-013: Specialist Organization Strategy - Maintaining Flat Structure

**Status**: Accepted
**Date**: 2025-11-22
**Scope**: Code Organization, Developer Experience

## Context

As of November 2025, the project contains 23 specialist classes in a single flat directory (`app/src/specialists/`). This fills approximately one full screen when viewing the directory listing, raising questions about whether reorganization would improve maintainability.

Two organizational approaches were considered:
1. **Type-based organization**: Group specialists by their technical characteristics (e.g., `llm_driven/`, `mcp_services/`, `orchestration/`)
2. **Domain-based organization**: Group specialists by their functional purpose (e.g., `file_ops/`, `analysis/`, `communication/`, `workflow/`)

### Current Specialist Inventory (23 Total)

**LLM-Driven Intent Interpreters** (5):
- file_operations_specialist.py
- batch_processor_specialist.py
- triage_architect.py
- systems_architect.py
- prompt_specialist.py

**MCP Service Layer** (1):
- file_specialist.py

**Artifact Processors** (6):
- text_analysis_specialist.py
- data_extractor_specialist.py
- data_processor_specialist.py
- structured_data_extractor.py
- sentiment_classifier_specialist.py
- web_builder.py

**Communication & Workflow** (5):
- chat_specialist.py
- response_synthesizer_specialist.py
- default_responder_specialist.py
- facilitator_specialist.py
- end_specialist.py

**Orchestration** (3):
- router_specialist.py
- prompt_triage_specialist.py
- critic_specialist.py

**Utilities & Examples** (3):
- archiver_specialist.py
- open_interpreter_specialist.py
- hello_world.py

### Emerging Architectural Context

Recent development revealed a key pattern distinction: **intent-interpreting specialists** (which parse user requests and create plans) require different infrastructure than **artifact-processing specialists** (which work on pre-gathered data). This distinction was discovered during the implementation of the `gathered_context` injection pattern, where 5 specialists needed a centralized helper method (`_get_enriched_messages()`) added to `BaseSpecialist`.

Additionally, the user identified that **some specialists may migrate to external MCP containers** in the near future, specifically mentioning:
> "fileops specialist and open_interpreter may work better or more powerfully through open source MCP containers"

This suggests the current 23-specialist count may decrease significantly once external MCP services (like the Node.js filesystem MCP server) are integrated.

## Decision

**Maintain the current flat specialist directory structure** (`app/src/specialists/`) without reorganization at this time.

Defer reorganization decisions until:
1. **MCP container migration** is complete (potentially reducing specialist count)
2. **Pattern-based abstractions** have matured (clearer type/domain boundaries emerge)
3. **Specialist count** remains high enough post-migration to justify organizational overhead

## Alternatives Considered

### Alternative 1: Type-Based Organization

**Structure**:
```
app/src/specialists/
├── llm_driven/          # Intent interpreters
├── mcp_services/        # Service layer
├── artifact_processors/ # Data transformers
├── orchestration/       # Routing & control flow
└── workflow/            # Communication & lifecycle
```

**Pros**:
- Groups specialists by implementation pattern
- Aligns with technical architecture (MCP services vs LLM-driven)
- Clear separation of concerns for testing strategies

**Cons**:
- Requires understanding internal implementation to locate functionality
- Categories may become ambiguous (e.g., chat_specialist is both LLM-driven AND workflow)
- High coupling between category definitions and implementation details
- May need restructuring as patterns evolve

### Alternative 2: Domain-Based Organization

**Structure**:
```
app/src/specialists/
├── file_operations/     # file_specialist, file_operations_specialist, batch_processor
├── analysis/            # text_analysis, data_extractor, sentiment_classifier
├── communication/       # chat, response_synthesizer, default_responder
├── workflow/            # router, triage, critic, facilitator, end
├── generation/          # web_builder, systems_architect, prompt_specialist
└── utilities/           # archiver, open_interpreter, hello_world
```

**Pros**:
- Intuitive for developers seeking functionality ("where's the file operations code?")
- Stable across refactoring (domain purpose changes less than implementation)
- Natural alignment with user-facing features
- Clear boundaries for documentation and testing

**Cons**:
- Some specialists span multiple domains (e.g., triage_architect is both workflow AND architecture)
- Cross-domain dependencies still exist (e.g., file_operations calls file_specialist MCP service)
- Requires consensus on domain boundaries

### Alternative 3: Wait-and-See (CHOSEN)

**Rationale**:
- Pending MCP migration may significantly reduce specialist count
- Current flat structure is functional (no critical pain points)
- Premature optimization avoided
- Domain/type boundaries will become clearer post-migration
- Infrastructure (BaseSpecialist helpers, MCP registry) is already addressing cross-cutting concerns

## Consequences

### Positive

1. **No Migration Overhead**: Avoids refactoring 23 files, updating imports, adjusting tests, and revising documentation
2. **Architectural Clarity**: MCP container integration can proceed without organizational distractions
3. **Pattern Discovery**: Allows natural evolution of type/domain boundaries before formalizing structure
4. **Future Flexibility**: Domain-based organization remains a viable option post-migration

### Negative

1. **Discoverability**: New developers must scan a full-screen directory listing to find specialists
2. **IDE Navigation**: No folder-based grouping for quick filtering (mitigated by IDE search/grep)
3. **Conceptual Grouping**: Related specialists (e.g., file_specialist + file_operations_specialist) not visually adjacent

### Mitigations

1. **Documentation**: Update [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) to include a categorized specialist inventory (similar to this ADR's context section)
2. **Naming Conventions**: Maintain descriptive names that include domain hints (e.g., `file_operations_specialist`, `text_analysis_specialist`)
3. **Revisit Trigger**: Document explicit conditions for reconsidering this decision:
   - Specialist count remains >15 after MCP migration
   - Developer onboarding feedback indicates discoverability issues
   - New architectural patterns emerge requiring physical separation

## Related Work

- **ADR-CORE-008**: MCP Architecture (completed) - Establishes service layer pattern that may reduce specialist count
- **ADR-MCP-002**: The Dockyard Architecture (not yet implemented) - Defines uploaded file handling that may replace some specialists
- **MCP Filesystem Server Reference**: Node.js implementation provided as example of external MCP container pattern

## Implementation Notes

This ADR documents a **decision to defer action**, not implement a change. No code modifications are required.

**Next Steps** (per user direction):
1. Focus on Docker MCP container integration
2. Investigate MCP filesystem server as replacement for internal file specialists
3. Revisit this ADR after MCP migration completes

## References

- Conversation: "Specialist Organization Analysis" (2025-11-22)
- User Quote: "I think sticking with a monolithic specialist folder should stay for the moment. I think instead we should focus on how to bring docker containers online."
- MCP Filesystem Server: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
