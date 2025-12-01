# Risk Assessment: Migration to Emergent Project Subgraph (RECESS Pattern)

## Executive Summary
We are pivoting from a "Linear Plan" architecture (rejected) to an "Emergent State Machine" (RECESS Pattern). This is a significant architectural shift that introduces complexity in exchange for adaptability.

## Critical Risks

### 1. State Isolation & Synchronization (High Risk)
*   **The Issue**: The `EmergentProjectSubgraph` will maintain its own internal state (`ProjectContext`). The main graph maintains `GraphState`.
*   **The Risk**: If `ProjectContext` is not correctly synchronized with `GraphState` (specifically `messages` and `artifacts`), the main graph (Router/Archiver) will have "amnesia" about what happened inside the subgraph.
*   **Mitigation**: Ensure the Subgraph's `exit` node explicitly merges the final `ProjectContext` artifacts back into the global `GraphState`.

### 2. The "Director Loop" Fragility (Medium Risk)
*   **The Issue**: The `ProjectDirector` (LLM) decides the next step based on context.
*   **The Risk**: The Director may get stuck in a loop (e.g., "Search -> Synthesize -> Search -> Synthesize") without making progress, or fail to recognize when the goal is met.
*   **Mitigation**:
    *   Implement a strict `iteration_limit` in `ProjectContext`.
    *   Inject a "Stagnation Detection" heuristic in the Director's prompt.
    *   Use the `Reviewer` node to force a "Stop and Think" moment.

### 3. Context Window Saturation (Medium Risk)
*   **The Issue**: A long-running research project will generate massive amounts of text (search results, drafts).
*   **The Risk**: The `ProjectContext` may exceed the LLM's context window, causing the Director to crash or hallucinate.
*   **Mitigation**:
    *   The `Synthesizer` must aggressively summarize raw search results into `known_facts`.
    *   Raw search results should be discarded from the context after synthesis, keeping only the distilled knowledge.

### 4. Regression of Simple Tasks (Low Risk)
*   **The Issue**: We are replacing the simple `ResearcherSpecialist` with a complex subgraph.
*   **The Risk**: Simple queries like "What is the capital of France?" might now trigger a heavy, multi-step "Project" workflow, increasing latency and cost.
*   **Mitigation**:
    *   The Main Router should distinguish between "Simple Question" (ChatSpecialist) and "Deep Research" (ProjectSubgraph).
    *   Configure the Subgraph to have a "Fast Path" for simple retrieval.

## Implementation Strategy
1.  **Commit Current State**: Save the "Linear Plan" work (even if rejected) to git history before deletion.
2.  **Clean Slate**: Remove the coupled `PlanExecutor` code to avoid confusion.
3.  **Iterative Build**: Build the `ProjectContext` and `Director` first, test them in isolation, then wire the Subgraph.

## Go/No-Go Criteria
*   **Go**: If `ProjectDirector` can successfully navigate a 3-step mock scenario (Search -> Synthesize -> Finish) in unit tests.
*   **No-Go**: If we cannot reliably sync `ProjectContext` back to `GraphState`.
