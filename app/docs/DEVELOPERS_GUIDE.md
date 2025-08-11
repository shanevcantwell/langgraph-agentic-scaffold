# [SYSTEM BOOTSTRAP] DEVELOPERS_GUIDE.md
# Project: SpecialistHub
# Version: 1.2
# Status: ACTIVE

## 1.0 CORE DIRECTIVE: MISSION & PHILOSOPHY

**Mission:** To construct a multi-agent system composed of modular, single-responsibility "Specialists." The system must be scalable, maintainable, and testable.

**Core Philosophy:** The system is composed of two primary types of agents:
1.  **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code). They inherit from `BaseSpecialist`.
2.  **Orchestrators:** High-level agents that manage a workflow by invoking other Specialists in a sequence. They contain their own internal `LangGraph` instance and do not typically call an LLM directly.

## 2.0 ARCHITECTURAL BLUEPRINT

The system is composed of the following layers and components.

### 2.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 2.2 The Orchestrator Pattern (e.g., ChiefOfStaffSpecialist)
*   **Role:** High-Level Workflow Manager.
*   **Implementation:** A standalone Python class (e.g., `ChiefOfStaffSpecialist`).
*   **Function:** An Orchestrator defines and executes a sub-graph. It takes a high-level goal and calls a series of Specialists in a predefined sequence to achieve it. It does **not** inherit from `BaseSpecialist`.

### 2.3 The Router/Supervisor Pattern
*   **Role:** Dynamic Decision Engine.
*   **Implementation:** A dedicated Specialist that inherits from `BaseSpecialist` (`RouterSpecialist`).
*   **Function:** Unlike a fixed-sequence Orchestrator, the Router dynamically decides the next step in a loop based on the current state. It is used for more flexible, cyclical execution models.

### 2.4 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist`. Must implement the `execute(state: GraphState) -> Dict[str, Any]` method.
*   **Function:** A Specialist performs a single atomic task, usually by calling an LLM. Its `execute` method contains the core logic for interacting with the LLM and processing the result.

### 2.5 Shared Resources: The Singleton Factory Pattern
*   **Principle:** To conserve resources and ensure consistency, critical services like LLM clients are managed as **Singletons**.
*   **Implementation:** The `LLMClientFactory` creates and caches a client for each provider. **Specialists do not create their own clients.**

## 3.0 FILE & NAMING SCHEMA (MANDATORY)

### 3.1 Directory Structure
.
|-- app/
|   |-- docs/
|   |   `-- DEVELOPERS_GUIDE.md
|   |-- prompts/
|   |   |-- data_extractor_specialist_prompt.md
|   |   |-- file_specialist_prompt.md
|   |   |-- prompt_specialist_prompt.md
|   |   |-- router_specialist_prompt.md
|   |   |-- systems_architect_prompt.md
|   |   `-- web_builder_prompt.md
|   `-- src/
|       |-- graph/
|       |-- llm/
|       |-- specialists/
|       |   |-- __init__.py
|       |   |-- base.py
|       |   |-- chief_of_staff.py
|       |   |-- data_extractor_specialist.py
|       |   |-- file_specialist.py
|       |   |-- prompt_specialist.py
|       |   |-- router_specialist.py
|       |   |-- systems_architect.py
|       |   `-- web_builder.py
|       `-- utils/
|           `-- prompt_loader.py
|
|-- .env
|-- main.py
`-- run.sh

### 3.2 Naming Convention
*   **Specialist Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains (e.g., `FileSpecialist` in `file_specialist.py`).
*   **Prompt Rule:** A prompt file in `app/prompts/` must be named `{specialist_name}_prompt.md`.

## 4.0 DEVELOPMENT PROTOCOLS

### 4.1 Protocol A: Creating a Standard Specialist (LLM-based)

1.  **Define Prompt Contract:** Create a new file in `app/prompts/` named `{specialist_name}_prompt.md`. Define the system prompt here.
2.  **Implement Specialist Logic:** Create a new file in `src/specialists/`. Use the following template:
    ```python
    from .base import BaseSpecialist
    from ..utils.prompt_loader import load_prompt
    from langchain_core.messages import HumanMessage

    class NewSpecialist(BaseSpecialist):
        def __init__(self, llm_provider: str):
            system_prompt = load_prompt("new_specialist") # Matches the prompt filename
            super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)

        def execute(self, state: dict) -> dict:
            # Your logic here. Get data from state.
            user_input = state.get("some_key")

            # Call the LLM via the base class invoke method
            ai_response = self.invoke({"messages": [HumanMessage(content=user_input)]})

            # Process the response and return the state update
            processed_output = ai_response["messages"][0].content
            return {"new_key": processed_output}
    ```
3.  **Integrate into a Graph:** Add your new specialist to an Orchestrator or Router graph.

### 4.2 Protocol B: Creating an Orchestrator Specialist

1.  **Define the Workflow:** Conceptualize the sequence of Specialists needed to accomplish a high-level task.
2.  **Implement the Orchestrator Class:** Create a new file in `src/specialists/`. This class will **not** inherit from `BaseSpecialist`. Use the `ChiefOfStaffSpecialist` as a template.
    *   The `__init__` method should accept instances of the Specialists it needs to call.
    *   Create methods for each step in your workflow that will serve as nodes in the graph (e.g., `call_systems_architect`). These methods will call the `.execute()` method of the specialist they are responsible for.
    *   Implement a `compile_graph` method that builds a `StateGraph` by adding the node methods and defining the edges (the sequence of operations).
    *   Create a public `invoke` method that serves as the entry point to the workflow.
3.  **Update the Main Entry Point:** In `app/src/main.py`, instantiate your new Orchestrator and the Specialists it requires, then call its `invoke` method with the initial goal.

## 5.0 CONFIGURATION: ENVIRONMENT VARIABLES

System configuration is managed via a `.env` file in the `/app` directory. The application uses the `python-dotenv` library to load these variables at runtime.

*   `LLM_PROVIDER`: **Required.** Sets the default LLM provider. Supported values: `"gemini"`, `"ollama"`, `"lmstudio"`.
*   `GOOGLE_API_KEY`: **Required for Gemini.** Your API key for the Google AI platform.
*   `GEMINI_MODEL`: *Optional.* The specific Gemini model to use (e.g., `gemini-1.5-flash`).
*   `OLLAMA_MODEL`: **Required for Ollama.** The name of the model to use with your local Ollama instance.
*   `OLLAMA_BASE_URL`: *Optional.* The base URL for the Ollama API (defaults to `http://localhost:11434`).
*   `LMSTUDIO_BASE_URL`: **Required for LM Studio.** The base URL for your local LM Studio server (e.g., `http://localhost:1234/v1`).
