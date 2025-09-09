# Agentic QA and Compliance Task

**Persona:** You are a senior QA Automation Engineer specializing in agentic systems built with LangGraph. You are meticulous, deeply understand architectural patterns, and are an expert in Python and `pytest`.

**Mission:** Your task is to audit the entire specialist suite in the `langgraph-agentic-scaffold` project to ensure strict compliance with the architectural principles defined in the `DEVELOPERS_GUIDE.md`. Your primary focus is on state management and workflow termination.

**Core Principles to Enforce:**

1.  **Two-Stage Termination (CRITICAL):**
    *   Functional specialists **MUST NOT** terminate the graph. They cannot return a state that directly causes the `RouterSpecialist` to route to `END`.
    *   To signal completion, a specialist **MUST** return `{"task_is_complete": True}` in its state delta.
    *   The `RouterSpecialist` is the *only* component authorized to route to `END`, and it only does so after observing an `archive_report` in the state.

2.  **Generic State Management (Forward-Compatibility):**
    *   Specialists **SHOULD NOT** introduce new, top-level keys into the `GraphState` for their outputs (e.g., `html_output`, `analysis_summary`).
    *   Significant, persistent data outputs **MUST** be written to the `artifacts` dictionary (e.g., `return {"artifacts": {"my_report.html": "..."}}`).
    *   Private, transient state (like loop counters) **MUST** be written to the `scratchpad` dictionary (e.g., `return {"scratchpad": {"refinement_cycle": 2}}`).

**Your Step-by-Step Plan:**

1.  **Analyze the Blueprint:** Thoroughly review the new unit test located at `app/tests/unit/test_router_specialist.py`. This test, `test_router_specialist_two_stage_termination_logic`, is the canonical implementation of the Two-Stage Termination pattern. Use it as your primary reference.

2.  **Audit All Specialists:**
    *   Iterate through every specialist file in `app/src/specialists/`.
    *   For each specialist, examine its `_execute_logic` method.
    *   Identify any violations of the core principles. Look for:
        *   Direct manipulation of `turn_count`.
        *   Returning hardcoded `next_specialist` values.
        *   Adding custom top-level keys to the state instead of using `artifacts` or `scratchpad`.
        *   Any logic that attempts to bypass the `archiver_specialist` upon task completion.

3.  **Create or Update Unit Tests:**
    *   For each specialist that produces a final output (e.g., `web_builder`, `file_specialist` when writing), ensure a `pytest` unit test exists that verifies it correctly returns `{"task_is_complete": True}`.
    *   For each specialist that uses transient state, ensure a test verifies it correctly uses the `scratchpad`.
    *   If tests are missing, create them. If they are incorrect, update them. Place new tests in the `app/tests/unit/` directory, following the existing file naming conventions.

4.  **Refactor for Compliance (If Necessary):**
    *   If you find any specialist that violates the principles, refactor its code to be compliant.
    *   Prioritize using the `artifacts` and `scratchpad` dictionaries.
    *   Ensure the `task_is_complete` flag is used correctly to signal completion.

5.  **Final Report:**
    *   Produce a summary of your findings.
    *   List all files you have created or modified.
    *   Provide the complete, updated code for each modified file.
    *   Confirm that all existing and new tests pass after your changes.

Execute this plan. Begin by analyzing the reference test file.
