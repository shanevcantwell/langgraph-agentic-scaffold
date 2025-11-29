# Emergent State Machine (ESM)

## Concept
The **Emergent State Machine (ESM)** is a pattern for allowing agents to dynamically define and track complex, multi-step workflows without hardcoding them into the graph structure.

Instead of a rigid `Graph` definition (e.g., `A -> B -> C`), the ESM allows an agent (like the `SystemsArchitect`) to write a "State Machine Definition" into the `artifacts` or `scratchpad`. Subsequent agents read this definition to know "Where are we?" and "What is next?".

## Data Structure
The ESM is a JSON object stored in `state["artifacts"]["emergent_state"]`.

```json
{
  "workflow_id": "recursive_file_search",
  "current_state": "scanning_root",
  "states": {
    "scanning_root": {
      "action": "list_directory",
      "target": ".",
      "next": "processing_subfolders"
    },
    "processing_subfolders": {
      "action": "iterate_list",
      "target": "gathered_context",
      "next": "analyzing_files"
    },
    "analyzing_files": {
      "action": "read_file",
      "condition": "contains_secret_word",
      "next": "complete",
      "fallback": "processing_subfolders"
    },
    "complete": {
      "action": "report_success"
    }
  },
  "variables": {
    "found_files": [],
    "visited_folders": ["."]
  }
}
```

## Benefits
1.  **Dynamic Workflows:** The system can invent new workflows on the fly (e.g., "I need to scrape 5 websites, then compare them, then write a report").
2.  **Resilience:** If the agent "blinks" (statelessness), the ESM object persists in the Graph State. The next agent reads `current_state: "processing_subfolders"` and knows exactly what to do.
3.  **Observability:** We can visualize the *emergent* logic of the agent, not just the hardcoded graph logic.

## Implementation Strategy
1.  **Planner:** The `SystemsArchitect` or `TriageArchitect` initializes the ESM object.
2.  **Executor:** The `Router` or a dedicated `StateExecutor` reads `current_state`, executes the action, and updates `current_state` to `next`.
3.  **Storage:** Stored in `artifacts` (for persistence) or `scratchpad` (for ephemeral loops).

## Use Cases
*   Recursive File Search (The "Walk the Tree" problem).
*   Multi-step Research Plans (Search -> Read -> Refine -> Search Again).
*   Code Refactoring Loops (Lint -> Fix -> Test -> Repeat).
