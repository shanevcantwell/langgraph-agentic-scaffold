# Research Directions

LAS serves as a workbench for studying how orchestration-layer interventions shape model behavior without touching weights.

## Prompt Geometry

semantic-chunker measures phrasing geometry in 768-d embedding space (embeddinggemma-300m default, NV-Embed-v2 4096-d available). RLHF shapes response space by making regions "cold" — phrasings geometrically distant from trained forms may hit unexplored regions. `analyze_variants` measures inter-phrasing distance to map these boundaries.

The hypothesis: if you can measure where phrasings land relative to trained response attractors, you can optimize orchestration-layer prompts without changing model weights.

## Explicit MoE as Interpretability

Specialist routing decisions are observable analogs of implicit MoE expert selection inside transformers. The Router's gating function is visible where TransformerLens can compare it with internal expert activation patterns.

This creates a correspondence: for a given input, LAS routes to specialist X. Inside the model, MoE routes to experts {A, B, C}. When external and internal routing agree, we have evidence the orchestration matches the model's internal specialization. When they diverge, we learn something about what the model "wants" to do versus what we're asking it to do.

## Context Engineering as Physics

Token positions create query-key geometries that determine inference trajectories. The Facilitator doesn't just assemble context — it constructs the experiential reality for each inference pass.

This framing treats prompt construction as a physics problem: tokens have positions, positions create attention geometries, geometries determine which information flows where. RoPE encodes spatial relationships. The order, proximity, and framing of context tokens are not metadata — they are the primary variables governing output.

## Semantic Contrast

Prompt decision-point quality measured via embedding-space drift between branches. When a prompt presents a choice (e.g., COMPLETED vs BLOCKED), higher pairwise embedding drift between the branch descriptions correlates with sharper model decision boundaries. This provides a quantitative signal for prompt engineering: if two options land in similar embedding neighborhoods, the model will struggle to distinguish them.
