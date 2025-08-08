# TODO: Enable Multi-Step Execution by Creating Graph Loops

## Objective
Refactor the main application graph to allow for multi-step agentic workflows. This involves modifying the graph's structure so that after a specialist node executes, control returns to the `RouterSpecialist` instead of terminating.

## Rationale
The current graph is linear (`Router -> Specialist -> END`) and can only execute single-step tasks. To enable complex commands like "Read file X and then summarize it," the graph must be able to loop, allowing the Router to chain multiple specialists together.

## Step-by-Step Plan

1.  **Open the main graph definition file:** This is likely `src/main.py` where the `StatefulGraph` object is instantiated and compiled.
2.  **Locate the conditional edge logic:** Find the function passed to `graph.add_conditional_edges()`. This function determines the next node after the `RouterSpecialist`.
3.  **Modify the graph structure:** The current logic likely has each specialist node pointing to `END`. This needs to change.
    *   After a specialist node (e.g., `file_specialist`, `prompt_specialist`) runs, the edge should now point back to the `router_specialist` node.
    *   This creates the loop: `Router -> Specialist -> Router`.
4.  **Update the Router's Prompt:** The `RouterSpecialist` needs a way to terminate the loop.
    *   Open `src/prompts/router_specialist.prompt`.
    *   Add `END` to the list of valid routing destinations.
    *   Add a rule for when to use `END`. For example: "If the user's request is a sign-off like 'thank you', 'that's all', or 'goodbye', or if the previous step seems to have fully answered the request, route to 'END'."
5.  **Update the Conditional Edge Function:** Modify the function from Step 2 to handle the new `END` route. If the router's output is `{'next_specialist': 'END'}`, the function should return the special `END` keyword. Otherwise, it should return the name of the next specialist node.

## Definition of Done
Run the application with a multi-step prompt, such as `python -m src.main "Read the README.md file and tell me what it says."`. Observe the console output. You should see the following execution sequence:
1.  `EXECUTING ROUTER` (routes to `file_specialist`)
2.  `EXECUTING FILE SPECIALIST`
3.  `EXECUTING ROUTER` (sees file content in state, routes to `prompt_specialist`)
4.  `EXECUTING PROMPT SPECIALIST`
5.  `EXECUTING ROUTER` (sees task is complete, routes to `END`)
The successful execution of this sequence confirms the loop is working.
