# Emergent Project Subgraph Architecture

## Overview

The **Emergent Project Subgraph** is a pattern for handling complex, open-ended tasks (like deep research) without relying on rigid, pre-defined plans. Instead of a linear list of steps, the system uses an **Emergent State Machine** where a controller (`ProjectDirector`) dynamically decides the next action based on the evolving state of the project (`ProjectContext`).

This architecture replaces the legacy "Linear Plan" model (SystemPlan/PlanExecutor), which proved too brittle for complex investigations.

## Core Components

### 1. Project Director (`ProjectDirector`)
*   **Role**: The "Brain" or Controller.
*   **Type**: LLM Specialist.
*   **Responsibility**:
    *   Maintains the `ProjectContext` (Goal, Knowledge Base, Open Questions).
    *   Analyzes results from workers.
    *   Decides the next best action (Search, Browse, or Complete).
*   **Prompt**: `app/prompts/project_director_prompt.md`

### 2. Web Specialist (`WebSpecialist`)
*   **Role**: The "Worker" or Execution Primitive.
*   **Type**: Procedural Specialist.
*   **Responsibility**:
    *   Executes a single, atomic web task (Search or Browse) from the scratchpad.
    *   Returns raw results.
    *   Has **NO** memory, planning capability, or awareness of the larger project.

### 3. Project Context (`ProjectContext`)
*   **Role**: The Shared State / Memory.
*   **Schema**: `app/src/interface/project_context.py`
*   **Fields**:
    *   `project_goal`: The user's original request.
    *   `knowledge_base`: List of confirmed facts.
    *   `open_questions`: List of uncertainties to resolve.
    *   `state`: Current phase (RESEARCHING, COMPLETE).
    *   `iteration`: Turn counter.

## The Loop (The "RECESS" Pattern)

The subgraph operates in a tight loop between the Director and the Worker:

1.  **Director** analyzes the `ProjectContext` and the last result.
2.  **Director** updates the `ProjectContext` (adds knowledge, removes questions).
3.  **Director** issues a command (e.g., "SEARCH for X") to the `scratchpad`.
4.  **Orchestrator** routes to **WebSpecialist**.
5.  **WebSpecialist** executes the command and returns results to the `scratchpad`.
6.  **Orchestrator** routes back to **ProjectDirector**.

This loop continues until the Director determines the goal is met (`COMPLETE`), at which point it returns control to the main Router.

## Advantages

*   **Resilience**: The system can adapt to unexpected findings or failures. If a search fails, the Director can try a different angle.
*   **Emergence**: The "plan" is not written in advance; it emerges from the interaction between the Director and the environment.
*   **Decoupling**: The Worker is a dumb primitive that can be easily swapped or upgraded. The Director holds all the intelligence.
