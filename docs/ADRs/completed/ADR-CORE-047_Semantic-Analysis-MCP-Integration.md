# ADR-CORE-047: Semantic Analysis MCP Integration

## Status
Completed (2026-02-12)

## Context

semantic-chunker provides embedding-based analysis tools useful for:
- Forensic study of text embeddings (prompt compliance geometry)
- Drift analysis across conversation archives
- Training data preparation (gemini-exporter deduplication)

These tools are batch/forensic in nature, not real-time monitors. The question is how to position them architecturally within LAS:
1. Which specialists (if any) should consume them directly?
2. Is there an active/emergent use case where users prompt LAS to analyze and rewrite content using embedding analysis?
3. What's the integration pattern (always-available vs. on-demand)?

### The Prompt Geometry Hypothesis

System prompts using imperative mood ("NEVER do X") may land in embedding regions that LLMs have learned to circumvent during RLHF training. Alternative grammatical structures (passive, presuppositional, descriptive) might achieve higher compliance by landing in less "trained-against" regions.

semantic-chunker can measure embedding distances between prompt variants, enabling empirical research into which phrasings are most effective.

## Decision

### Integration Layer: Optional External MCP

Add semantic-chunker as an optional external MCP service, not woven into core execution:

```yaml
# config.yaml
mcp:
  external_mcp:
    services:
      semantic-chunker:
        enabled: true
        required: false  # Graceful degradation if not installed
        command: "python"
        args: ["-m", "semantic_chunker.mcp.server"]
        timeout_ms: 30000
```

Installation: `pip install -e ../semantic-chunker` (sibling repo, editable install)

### Available Tools

| Tool | Description | Primary Consumer |
|------|-------------|------------------|
| `analyze_variants` | Embed prompt variants, calculate distances from baseline | Research/offline analysis |
| `generate_variants` | LLM-generate grammatical alternatives to a constraint | Research/offline analysis |
| `calculate_drift` | Cosine distance between two texts | BatchProcessorSpecialist, research |
| `embed_text` | Raw embedding vector for text | General utility |
| `dedup_conversation` | Clean gemini-exporter JSON | Pipeline/batch processing |

### Specialist Access Pattern

**All specialists** receive `external_mcp_client` via GraphBuilder injection (existing pattern). Any specialist CAN call semantic-chunker tools, but primary consumers are:

1. **BatchProcessorSpecialist** - For processing conversation archives, calculating drift across outputs
2. **Future: PromptEngineeringSpecialist** - For the emergent use case below
3. **Research/CLI tooling** - Not runtime graph, but available for offline analysis

### Emergent Use Case: Prompt Rewriting for Semantic Novelty

A user could prompt LAS:

> "Here is a CLAUDE.md set of rules for Claude Code. Rewrite the imperative constraints to maximize semantic distance from the baseline while preserving meaning. Target embedding distance > 0.3 from original."

This requires a specialist that:
1. Parses the input document for imperative constraints
2. Calls `generate_variants` for each constraint
3. Calls `analyze_variants` to measure distances
4. Selects variants exceeding the threshold
5. Reconstructs the document with optimized phrasings

**Question: Should this be a dedicated specialist, or a capability of an existing one?**

Options:
- **A) New PromptEngineeringSpecialist** - Dedicated to prompt analysis and optimization
- **B) Extend SystemsArchitectSpecialist** - Already handles design/analysis tasks
- **C) No specialist** - CLI tool only, not routable via graph
- **D) General-purpose with tool access** - Route to ChatSpecialist with semantic-chunker tools available

### Threshold-Based Semantic Novelty

The "exceed threshold" pattern could generalize:

```python
# Pseudocode for threshold-based rewriting
for constraint in parse_imperatives(document):
    variants = generate_variants(constraint)
    distances = analyze_variants(variants, baseline=constraint)

    # Select variant with max distance above threshold
    best = max(
        [(v, d) for v, d in distances.items() if d > threshold],
        key=lambda x: x[1],
        default=None
    )

    if best:
        replacements[constraint] = best[0]
```

This is novel enough to warrant research validation before productionizing.

## Alternatives Considered

### A) Infrastructure Integration (Rejected)
Bake drift monitoring into SafeExecutor - every specialist output compared to previous turn.

**Rejected because:** semantic-chunker tools are forensic/batch, not real-time monitors. The overhead of embedding every turn isn't justified for the use cases.

### B) Dedicated SemanticAnalysisSpecialist (Deferred)
A specialist routable for "compare these texts" or "analyze this prompt" queries.

**Deferred because:** Unclear if routing to this is better than making tools available to existing specialists. Revisit after validating the prompt geometry hypothesis.

### C) No LAS Integration (Rejected)
Keep semantic-chunker as CLI-only tooling.

**Rejected because:** MCP integration is low-cost and enables the emergent use case. The infrastructure (ExternalMcpClient) already exists.

## Version Identification

**MCP "servers" are versioned code snapshots with a standardized interface.** Unlike a live service with a potentially changing API, an MCP module is frozen at the version you installed. This makes version tracking critical.

### Requirements

1. **semantic-chunker must expose version in tool responses:**
   ```python
   # Every tool response includes version metadata
   return {
       "result": ...,
       "_meta": {
           "semantic_chunker_version": "0.4.2",
           "mcp_protocol_version": "1.0"
       }
   }
   ```

2. **LAS should log which version is connected at startup:**
   ```
   INFO: Connected to semantic-chunker v0.4.2 (mcp protocol 1.0)
   ```

3. **Archive manifests should record tool versions used:**
   ```json
   {
     "mcp_services": {
       "semantic-chunker": "0.4.2",
       "filesystem": "1.2.0"
     }
   }
   ```

This enables debugging "this worked last week" scenarios - you can check if the tool version changed.

## Consequences

### Positive
- Low integration cost (config.yaml + pip install, same as any Python package)
- Enables empirical prompt engineering research
- Tools available for batch processing pipelines
- Future Sleeptime Compute can leverage the MCP pathway
- Standardized interface means LAS doesn't couple to semantic-chunker internals

### Negative
- Prompt geometry hypothesis is unvalidated - may not pay off
- Emergent use case requires specialist work to be useful
- Version drift between repos requires attention (same as any cross-repo dependency)

### Open Questions (Annotated Feb 2026)

1. **Which option for the emergent use case?** (A/B/C/D above) — **Resolved: Option D in practice.** Text Analysis Specialist consumes semantic-chunker tools via prompt-prix `react_step` MCP. TA acts as a general-purpose specialist with tool access, not a dedicated semantic analysis specialist. This aligns with Option D (general-purpose with tool access) without requiring a new specialist.
2. **Should we validate the prompt geometry hypothesis first?** — **Yes, and calibration is underway.** Drift measurements validated empirically (see Implementation Notes). The hypothesis hasn't been fully tested for compliance correlation, but the measurement infrastructure is operational.
3. **Threshold values?** What embedding distance is meaningful? — **Resolved: 0.3 in embeddinggemma-300m (768-dim) space.** Correct file categorizations show ~0.25-0.28 drift. 0.3 is the "semantic squelch" threshold — above this, responses are meaningfully different from expected.

## Verification

1. **Integration test:** Call `calculate_drift` from BatchProcessorSpecialist
2. **CLI test:** `python -m semantic_chunker.mcp.server` responds to tool calls
3. **Research validation:** Manual prompt geometry experiments before specialist work

## Related

- ADR-CORE-027: Navigation MCP Integration (pattern reference)
- ADR-CORE-035: Filesystem Architecture Consolidation (external MCP pattern)
- ADR-CORE-048: Confidence-Based Governance (complementary signal source)
- semantic-chunker ADR-007: Prompt Compliance Geometry Analysis
- Cathedral & Codex: Blueprint 9 (Guild of Judges), Blueprint 10 (Hierarchy of Wisdom)
- Future: Sleeptime Compute integration

---

## Implementation Notes (Feb 2026)

### Integration Operational

semantic-chunker MCP is wired and operational. All 5 MCP containers (filesystem, terminal, surf, semantic-chunker, prompt-prix) are reachable from the app container via `docker exec`.

### Validated MCP Chain

The full three-container chain is validated end-to-end:

```
NL prompt → Triage → Text Analysis Specialist
    → prompt-prix react_step (MCP)
        → semantic-chunker calculate_drift (MCP) × N
    → velocity/acceleration table
    → HTML report
```

This validates that semantic-chunker tools are consumable through the prompt-prix `react_step` MCP pattern, not just direct MCP calls. The indirection (LAS → prompt-prix → semantic-chunker) works because `react_step` forwards tool calls to the appropriate MCP server.

### Drift Calibration

Empirical calibration in embeddinggemma-300m (768-dim) space:

| Measurement | Drift Value |
|-------------|-------------|
| Correct file categorizations | ~0.25-0.28 |
| Semantic squelch threshold | 0.3 |
| Opposite/unrelated content | >0.5 |

The 0.3 threshold has proven reliable for distinguishing "close enough" from "meaningfully different" in production file categorization tasks.

### judge() Deprecated

`judge()` (LLM-as-judge) deprecated in favor of `calculate_drift` / `analyze_trajectory`. Embedding distance is more reproducible — same inputs always produce the same distance score, unlike LLM-as-judge which varies across runs and models.

### Consumer Pattern: TA via react_step

Rather than wiring semantic-chunker directly to individual specialists (the original proposal's pattern), the actual consumption flows through prompt-prix's `react_step` MCP tool. TA requests a ReAct iteration; `react_step` dispatches tool calls to semantic-chunker on TA's behalf. This keeps the tool-forwarding chain clean — specialists don't need to know which MCP server hosts which tool.

### What Remains

- **Prompt geometry hypothesis validation**: Infrastructure is ready (drift measurement, variant generation). The hypothesis that alternative grammatical structures achieve higher compliance by landing in less "trained-against" embedding regions hasn't been formally tested yet.
- **Dedup/pipeline tools**: `dedup_conversation` (gemini-exporter cleanup) is available but hasn't been integrated into a LAS workflow.
- **Version identification**: The `_meta` response field pattern proposed in this ADR hasn't been implemented in semantic-chunker's tool responses yet. Version tracking is informal (container image tags).
