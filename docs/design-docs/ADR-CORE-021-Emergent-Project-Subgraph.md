# ADR-CORE-021: Emergent Project Subgraph (The RECESS Pattern)

## Status
**PROPOSED**

## Context
We initially attempted to implement "Deep Research" using a **Linear Plan** model (`PlanExecutor` + `SystemPlan`). This proved too rigid and introduced tight coupling between workers and the executor.

**The Failure Mode**:
1.  **Rigidity**: A linear list cannot adapt to emergent discoveries without complex re-planning.
2.  **Coupling**: `WebSpecialist` was hard-wired to `PlanExecutor`, violating the "dumb worker" principle.
3.  **Role Confusion**: Workers were managing state (advancing plan indices).

## The Solution: Emergent State Machine (ESM)
We will adopt the **RECESS Pattern** (Emergent State Machine) to create a generic **Emergent Project Subgraph**. This subgraph can be instantiated for various domains (Research, Coding, Design) but follows a common architectural pattern.

### 1. The Philosophy
*   **Subgraph as a Service**: The subgraph is a self-contained cognitive engine. It accepts a `Goal` and returns a `Result`.
*   **Controller-Worker Pattern**: A `ProjectDirector` (LLM) acts as the central controller. Workers are pure primitives.
*   **No Hard Edges Between Workers**: Workers *never* call other workers. They return results to the Controller (or a convergence point).
*   **Emergent State**: The state is not a list of steps, but a snapshot of *current progress* (Context).

### 2. The Components

#### A. The State (`ProjectContext`)
A generic state model that tracks the project's evolution.
```python
class ProjectContext(BaseModel):
    goal: str
    domain: str # "research", "coding", "design"
    
    # Knowledge/Artifacts
    known_facts: List[str]
    artifacts: Dict[str, Any] # Code files, designs, etc.
    
    # Process State
    open_questions: List[str]
    completed_tasks: List[str]
    current_focus: str
    
    status: str # "active", "converged", "stuck"
```

#### B. The Controller (`ProjectDirector`)
*   **Role**: The "Context_Router" of the subgraph.
*   **Input**: The `ProjectContext`.
*   **Output**: A routing decision (`ProjectDecision`).
*   **Logic**:
    1.  Analyze `ProjectContext`.
    2.  Determine the next necessary capability (Search, Code, Design, Critique).
    3.  Route to the appropriate Worker.

#### C. The Workers (Primitives)
Workers are "dumb". They take inputs (from `scratchpad` or `state`) and return outputs. They do NOT know about the `ProjectContext` or the `Director`.
*   **`WebSpecialist`**: Search/Browse.
*   **`FileSpecialist`**: Read/Write files.
*   **`Synthesizer`**: Updates the `ProjectContext` (adds facts, removes questions).
*   **`Critic`**: Optional quality control loop.

### 3. The Flow (The Loop)
1.  **Entry**: Main Router routes to `ProjectSubgraph` (with a Goal).
2.  **Director**: Analyzes Goal. Decides "I need to search for X".
3.  **Router**: Routes to `WebSpecialist`.
4.  **Worker (`WebSpecialist`)**: Executes search. Returns results to State.
5.  **Director**: Sees new results. Decides "I need to synthesize this".
6.  **Router**: Routes to `Synthesizer`.
7.  **Worker (`Synthesizer`)**: Updates `ProjectContext`.
8.  **Director**: Re-evaluates. If goal met -> FINALIZE. Else -> Loop.

### 4. Integration
*   The subgraph is exposed as a capability (e.g., `deep_research_specialist` or `project_manager`).
*   The Main Router provides the `Goal`.
*   The Subgraph returns the `Final Artifact`.

## Benefits
1.  **Decoupling**: Workers are reusable primitives.
2.  **Adaptability**: The Director can pivot instantly based on worker results.
3.  **Observability**: The `ProjectContext` provides a clear snapshot of the project's state at any moment.

## Next Steps
1.  **Delete** `PlanExecutor` and `SystemPlan`.
2.  **Refactor** `WebSpecialist` to be a pure primitive.
3.  **Implement** `ProjectContext` and `ProjectDirector`.
4.  **Build** `ProjectSubgraph` wiring.
