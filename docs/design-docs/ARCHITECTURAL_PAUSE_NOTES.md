# Architectural Pause Notes - Nov 30, 2025

## Status Quo (Where we stopped)

We have partially implemented a **"Manager-Worker"** pattern to support Architect-Driven Research.

### 1. The Primitives
*   **`WebSpecialist` (The Hands)**: 
    *   Refactored to be a "dumb" primitive.
    *   Executes a single capability (`search`) based on input.
    *   Does **not** manage state or loops.
    *   *Status*: Implemented in `app/src/specialists/web_specialist.py`.

*   **`PlanExecutor` (The Foreman)**:
    *   New procedural specialist.
    *   Updates the `SystemPlan` (marks steps complete/failed).
    *   Decides if the plan is finished.
    *   *Status*: Implemented in `app/src/specialists/plan_executor.py`.

### 2. The State
*   **`SystemPlan`**:
    *   A Pydantic model defining a linear list of `ExecutionStep`s.
    *   Includes `assigned_to` field for task delegation.
    *   *Status*: Defined in `app/src/interface/system_plan.py`.

### 3. The Wiring (GraphBuilder & Orchestrator)
*   **Conditional Loop**:
    *   `WebSpecialist` -> `PlanExecutor` (if `SystemPlan` is active).
    *   `PlanExecutor` -> `Router` (via `check_plan_status`).
    *   `Router` (via `check_plan_status`) -> `WebSpecialist` (next step).
*   *Status*: Logic added to `GraphOrchestrator`, wiring added to `GraphBuilder`.

## The Architectural Divergence

The user identified a conflict between the **Linear Plan** model we are building and the **Iterative Refinement** model (Critique Subgraph) that was the original "Hello World".

### The Conflict
*   **Current Path (PlanExecutor)**: Pushes a stack of tasks. "Do A, then B, then C." Good for structured research.
*   **Original Vision (Critique)**: "Draft X, Critique it, Revise X." Emergent quality improvement.
*   **The Risk**: `PlanExecutor` is becoming a rigid task runner that ignores the *emergent* needs of a complex task (like "designing a website"). It assumes the Architect knows all steps in advance.

### The "Emergent State Management" Gap
The user suggests we need a "proper architecting of an Emergent State Management subgraph". This implies:
1.  The "Plan" shouldn't just be a static list.
2.  The "Manager" needs to handle *dynamic* additions to the plan (e.g., "Oh, that search failed, let's try this instead" or "The design is good but needs better CSS").
3.  The current `PlanExecutor` is too procedural/dumb for this.

## Next Steps for Discussion
1.  **Reconcile Plan vs. Critique**: How do we combine "doing a list of things" with "refining a thing"?
2.  **Emergent State**: How do we allow the plan to evolve during execution without turning `PlanExecutor` into another LLM Router?
3.  **Subgraph Definition**: Should "Deep Research" be its own isolated subgraph rather than main graph nodes?
