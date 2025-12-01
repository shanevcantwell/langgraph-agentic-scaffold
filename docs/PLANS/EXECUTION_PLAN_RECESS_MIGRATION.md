# Execution Plan: Migration to Emergent Project Subgraph (RECESS Pattern)

## Phase 1: Cleanup (The "Undo")
We need to remove the components of the rejected "Linear Plan" architecture to clear the way for the new design.

*   [ ] **Step 1.1**: Remove `PlanExecutor` specialist.
    *   *Action*: Delete `app/src/specialists/plan_executor.py`.
*   [ ] **Step 1.2**: Remove `SystemPlan` schema.
    *   *Action*: Delete `app/src/interface/system_plan.py`.
*   [ ] **Step 1.3**: Unwire `PlanExecutor` from `GraphBuilder`.
    *   *Action*: Edit `app/src/workflow/graph_builder.py` to remove the `WebSpecialist <-> PlanExecutor` loop and conditional edges.
*   [ ] **Step 1.4**: Remove `plan_executor_specialist` from `config.yaml`.
    *   *Action*: Edit `config.yaml`.

## Phase 2: Foundation (The "New State")
We will define the generic state and controller for the Emergent Project Subgraph.

*   [ ] **Step 2.1**: Define `ProjectContext` Schema.
    *   *Action*: Create `app/src/interface/project_context.py`.
    *   *Content*: Pydantic models for `ProjectContext`, `Task`, and `ProjectStatus`.
*   [ ] **Step 2.2**: Create `ProjectDirector` Specialist.
    *   *Action*: Create `app/src/specialists/project_director.py`.
    *   *Role*: The "Context Router" (LLM) that analyzes `ProjectContext` and decides the next `Task`.
*   [ ] **Step 2.3**: Create `ProjectDirector` Prompt.
    *   *Action*: Create `app/prompts/project_director_prompt.md`.
    *   *Content*: Instructions for analyzing state and assigning tasks.

## Phase 3: Wiring (The "Subgraph")
We will build the reusable subgraph structure.

*   [ ] **Step 3.1**: Create `EmergentProjectSubgraph` Class.
    *   *Action*: Create `app/src/workflow/subgraphs/emergent_project.py`.
    *   *Logic*: Implements the `Director -> Worker -> Synthesizer -> Director` loop.
*   [ ] **Step 3.2**: Wire Subgraph into `GraphBuilder`.
    *   *Action*: Edit `app/src/workflow/graph_builder.py` to instantiate and register the subgraph.

## Phase 4: Configuration (The "Research Profile")
We will instantiate the generic subgraph for the "Deep Research" use case.

*   [ ] **Step 4.1**: Configure `deep_research_specialist` in `config.yaml`.
    *   *Action*: Add entry pointing to the `EmergentProjectSubgraph` with `profile: research`.
*   [ ] **Step 4.2**: Ensure `WebSpecialist` is ready.
    *   *Action*: Verify `app/src/specialists/web_specialist.py` is a pure primitive (it should be, from previous steps).

## Phase 5: Verification
*   [ ] **Step 5.1**: Run `runverify.sh` to ensure no regressions.
*   [ ] **Step 5.2**: Test a research query (e.g., "Research the history of the RECESS pattern").
