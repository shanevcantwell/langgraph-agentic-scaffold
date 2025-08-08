# PROPOSAL: Implement a Formal Testing Framework

## Objective
To architect and implement a formal, automated testing harness for the project. This framework is the next logical step in maturing the codebase, following the successful consolidation outlined in `TODO_[completed]_Consolidate_Codebase.md`.

## Rationale
The current development process relies on manual smoke tests, which are insufficient for a system of this complexity. This approach creates a high risk of regressions and directly contradicts the principles of building reliable, "intelligent objects" as defined in `DEVELOPERS_GUIDE.md`.

Implementing a formal test suite is critical for enabling future work, such as the tasks outlined in `TODO_[to_triage]_Enable_Graph_Loops.md` and `TODO_[to_triage]_Singleton_LLM_Client.md`, as it provides the necessary stability to refactor and add features with confidence.

## Architectural Vision

The testing harness will be built on two pillars: **Unit Tests** and **Integration Tests**, using the `pytest` framework.

1.  **Unit Tests:** Each specialist will be tested in complete isolation. All external dependencies, particularly network calls to the Gemini API, will be "mocked" (simulated). This ensures tests are fast, deterministic, and test our internal logic, not external services.
2.  **Integration Tests:** A smaller set of tests will validate the interactions between specialists within the compiled LangGraph graph.
3.  **Directory Structure:** All test code will reside in a top-level `tests/` directory, keeping it distinctly separate from the application source code in `src/`.

    ```
    langgraph-agentic-scaffold/
    ├── src/
    ├── tests/
    │   ├── unit/
    │   └── integration/
    ├── requirements.txt
    └── ...
    ```

This proposal greenlights the work detailed in `TODO_03_Build_Test_Case_Framework.md`.
