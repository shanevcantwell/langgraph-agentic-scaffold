# Deep Research Execution Plan: Phase 1 (The Primitive)

## Overview
This plan details the immediate steps to convert the "Agentic Researcher" into the "WebSpecialist Primitive" and wire the "Conductor" logic to drive it. This is the foundational "Hands" layer of the Deep Research architecture.

## 1. The Primitive (Refactor & Rename)
**Target:** `app/src/specialists/researcher_specialist.py` → `app/src/specialists/web_specialist.py`
*   [ ] **Rename:** Rename file and class (`ResearcherSpecialist` → `WebSpecialist`).
*   [ ] **Strip Agent Logic:** Delete `_execute_logic`. The specialist will no longer have an LLM loop; it becomes a pure MCP tool provider.
*   [ ] **Expose Tools:** Ensure `register_mcp_services` exposes the `search` tool (backed by the Strategy Pattern).

## 2. The Configuration (Registry Update)
**Target:** `config.yaml` & `app/src/enums.py`
*   [ ] **Update Enum:** Replace `RESEARCHER = "researcher_specialist"` with `WEB = "web_specialist"` in `app/src/enums.py`.
*   [ ] **Update Config:** Rename configuration key in `config.yaml` and add strategy config:
    ```yaml
    web_specialist:
      enabled: true
      class: "app.src.specialists.web_specialist.WebSpecialist"
      search_strategy: "duckduckgo"
    ```

## 3. The Wiring (Graph Construction)
**Target:** `app/src/workflow/graph_builder.py`
*   [ ] **Load Specialist:** Update `_load_and_configure_specialists` to listen for `web_specialist`.
*   [ ] **Inject Strategy:** Inject `DuckDuckGoStrategy` into `WebSpecialist` instance during construction.
*   [ ] **Add Node:** Ensure `WebSpecialist` is added to the graph as a node.

## 4. The Conductor (Orchestration Logic)
**Target:** `app/src/workflow/graph_orchestrator.py`
*   [ ] **Implement Plan Execution:** Add `check_plan_status` logic to routing:
    1.  Check if `state["artifacts"]["system_plan"]` exists.
    2.  Check if status is `in_progress`.
    3.  Check if `next_step` is a known primitive (e.g., "search").
    4.  **Action:** Route *directly* to `web_specialist` (bypassing Router LLM).

## 5. The Planner (Prompt Engineering)
**Target:** `app/prompts/systems_architect_prompt.md`
*   [ ] **Update Prompt:** Explicitly grant "Research" capability.
    *   *Instruction:* "You are the Planner. When you need external information, create a `SystemPlan` with execution steps."
    *   *Tools:* List `WebSpecialist` (Search) as an available execution capability.

## 6. Verification
*   [ ] **Test:** Verify that asking "Research X" routes to Architect -> WebSpecialist -> Output.
