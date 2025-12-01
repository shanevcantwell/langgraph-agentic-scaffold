# Deep Research Phase 1: Risk Assessment & Testing Plan

## 1. Risk Assessment

| Risk | Probability | Impact | Description | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| **Orchestrator Loops** | Medium | High | The "Conductor" logic might fail to advance the plan state, causing an infinite loop (Architect ↔ WebSpecialist). | Implement strict state transitions in `GraphOrchestrator`. Ensure `SystemPlan` steps are marked `completed` explicitly. |
| **Router Confusion** | Medium | Medium | The Router might try to send "Research" intents directly to `WebSpecialist` (treating it as a chat agent) instead of the Architect. | Remove `WebSpecialist` from the Router's LLM routing menu. It should only be accessible via the Orchestrator's plan logic. |
| **Prompt Fragility** | High | Medium | The `SystemsArchitect` might generate malformed `SystemPlan` JSON that the Orchestrator cannot parse or execute. | Add robust few-shot examples to the Architect's prompt. Implement defensive parsing in the Orchestrator. |
| **Artifact Blindness** | Low | High | The Architect might not know where to find the search results (`artifacts["search_results"]`) after the primitive runs. | Explicitly document the artifact schema in the Architect's system prompt. |
| **Config Breakage** | Low | High | Renaming `researcher_specialist` to `web_specialist` in code but missing it in `config.yaml` will crash the app. | Comprehensive grep search for all references before running. |

## 2. Testing Plan

### 2.1 Unit Tests (The Components)
*   **`WebSpecialist`:** Verify it initializes with the Strategy and executes `search` without an LLM loop.
*   **`GraphOrchestrator`:** Test the `check_plan_status` function with mock states:
    *   *Input:* Plan with `status="in_progress"`, `next_step="search"`.
    *   *Output:* Should return `"web_specialist"`.
    *   *Input:* Plan with `status="completed"`.
    *   *Output:* Should return `"router"` (or next logic).

### 2.2 Integration Scenarios (The Flow)
*   **Scenario A: The "Hello World" of Research**
    *   *Prompt:* "Find the release date of Python 3.13."
    *   *Expected Trace:* `Router` → `SystemsArchitect` (Plan) → `WebSpecialist` (Search) → `SystemsArchitect` (Read & Answer).
    *   *Success Criteria:* The final answer contains the correct date, and the `SystemPlan` artifact shows the search step as completed.

*   **Scenario B: The "Multi-Step" (Sequential)**
    *   *Prompt:* "Search for the top 3 AI news items, then browse the first one."
    *   *Expected Trace:*
        1.  `Architect` plans Search.
        2.  `WebSpecialist` executes Search.
        3.  `Architect` updates plan to Browse (using URL from results).
        4.  `WebSpecialist` executes Browse.
        5.  `Architect` synthesizes.
    *   *Success Criteria:* The system transitions correctly between steps without getting stuck.

### 2.3 Rollback Plan
If the refactor causes critical instability:
1.  Revert the `enums.py` and `config.yaml` changes.
2.  Restore `researcher_specialist.py` from git history.
3.  Disable the `check_plan_status` logic in `GraphOrchestrator`.
