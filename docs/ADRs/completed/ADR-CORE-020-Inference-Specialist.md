# ADR-CORE-020: The InferenceSpecialist (The Pure Reasoning Engine)

## Status
**Implemented** (2026-01-17)

## Implementation Notes

InferenceService is implemented at `app/src/mcp/services/inference_service.py` with:
- `infer(context, question, output_format, llm_adapter)` - Generic semantic inference
- `judge_relevance(query, content, llm_adapter)` - Relevance filtering
- `detect_contradiction(claim_a, claim_b, llm_adapter)` - Semantic comparison
- `assess_source_quality(url, content, llm_adapter)` - Source evaluation

**Adapter Pattern Decision:** InferenceService uses the **calling specialist's adapter** rather than a dedicated binding. This avoids a config system gap where MCP services can't get adapters through `specialist_model_bindings`. See ADR-MCP-004 for future discussion of MCP services that need to call specific LLMs independently.

## Context
We have identified a critical gap in the current "Agentic" architecture, termed the **"Agentic Quantization Problem"**.
By forcing all cognition into discrete tool calls (Search, Code, File) or routing decisions, the system loses the LLM's native superpower: **Continuous Semantic Reasoning**.
We have observed the system "thrashing" (e.g., trying to write Python code to compare natural language strings) because it lacks a component dedicated to pure thought.

## Decision
We will implement the **`InferenceSpecialist`** as a dedicated "Brain" primitive.

### 1. Role & Responsibility
*   **The "Brain":** A specialist dedicated to pure semantic judgment, ambiguity resolution, and nuance detection.
*   **No Tools:** It has **zero** tools. It cannot search, code, or read files. Its only input is context; its only output is inference.
*   **No Persona:** It is not a "character". It is a raw reasoning engine.

### 2. Implementation Pattern: MCP Service vs. Graph Node
We will implement the `InferenceSpecialist` primarily as an **Internal MCP Service**, but wrap it as a Graph Node for specific workflows.
*   **Primary Use (Synchronous Subroutine):** Other specialists (e.g., `SystemsArchitect`, `WebSpecialist`) can call it synchronously via MCP to make judgment calls *during* their execution.
    *   *Example:* Architect asks: "Is this search result relevant to the user's goal?" -> InferenceSpecialist returns "No".
*   **Secondary Use (Graph Node):** The Router can route to it for pure reasoning tasks that don't require tools.

### 3. Interface (The Contract)
The `InferenceSpecialist` exposes a single, flexible MCP tool: `infer`.

```python
class InferenceRequest(BaseModel):
    context: str = Field(..., description="The raw text or data to analyze.")
    question: str = Field(..., description="The specific judgment or inference to make.")
    output_format: Optional[str] = Field(None, description="Optional schema hint (e.g., 'boolean', 'json').")

class InferenceResponse(BaseModel):
    judgment: Any = Field(..., description="The result of the inference.")
    reasoning: str = Field(..., description="The chain of thought leading to the judgment.")
    confidence: float = Field(..., description="0.0 to 1.0 confidence score.")
```

### 4. Use Cases
1.  **Ambiguity Resolution:** "Is the user asking to read a file or write a file?" (Solves the thrashing problem).
2.  **Relevance Filtering:** "Is this search result actually useful?" (Solves the 'Synthesizer guessing' problem).
3.  **Semantic Comparison:** "Do these two documents contradict each other?" (Solves the 'Code for NLP' problem).
4.  **Sanity Checking:** "Does this plan make sense?" (Solves the 'Over-engineering' problem).

## Rationale
*   **The Reasonable Agent Test:** Agentic behavior (tools/routing) is justified for *discrete actions*. Pure semantic processing requires an `InferenceSpecialist`.
*   **Efficiency:** Prevents "Planning to Plan" loops by resolving ambiguity instantly.
*   **Nuance:** Restores the continuous embedding-space reasoning that agentic architectures often quantize away.

## Consequences
*   **Cost:** Adds LLM calls, but likely *saves* tokens by preventing failed loops and hallucinations.
*   **Architecture:** Requires specialists to have access to the `InferenceSpecialist` via MCP (which is already supported by the `McpRegistry`).

## Alignment
*   **Cathedral:** This is the "Cognitive Co-Processor" for raw intelligence.
*   **Deep Research:** Acts as the "Brain" to the WebSpecialist's "Hands".
*   **HitL:** Acts as the "Pre-Brake" logic—detecting when to trigger `clarification_required`.
