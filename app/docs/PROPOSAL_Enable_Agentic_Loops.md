# PROPOSAL: Enable Agentic Loops in the Graph

## Objective
To evolve the core graph architecture from a simple Directed Acyclic Graph (DAG) to one that supports cycles, enabling iterative and reflective agentic behaviors.

## Rationale
The most powerful agentic patterns, such as the "Reflect" pattern seen in the `deep_researcher`'s `reflect_on_summary` node, rely on the ability to loop. An agent must be able to evaluate its own work and decide to retry a step or take a different approach.

Enabling loops will unlock advanced capabilities, including:
*   **Self-Correction:** The agent can review its output against a set of criteria and re-run a step if it fails.
*   **Iterative Refinement:** The agent can progressively build on a result over multiple turns (e.g., writing a draft, then revising it).
*   **Tool-Use Retries:** If a tool call fails, the agent can loop back and attempt to call it again with different parameters.

## Architectural Vision
This will require modifying the graph's conditional routing logic to allow edges to point to preceding nodes. To manage this new complexity and prevent infinite loops, we will also enhance the `AgentState` to include:
1.  **An Iteration Counter:** A simple integer that increments with each loop.
2.  **Explicit Exit Conditions:** The graph's logic will be designed to terminate a loop when a maximum number of iterations is reached or a specific success criterion is met (e.g., a `final_answer` key is populated in the state).
The LangSmith integration will be essential for debugging the behavior of these loops.
