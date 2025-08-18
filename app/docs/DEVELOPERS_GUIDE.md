# [SYSTEM BOOTSTRAP] DEVELOPERS_GUIDE.md
# Project: SpecialistHub
# Version: 2.0
# Status: ACTIVE

## 1.0 CORE DIRECTIVE: MISSION & PHILOSOPHY

**Mission:** To construct a multi-agent system composed of modular, single-responsibility "Specialists." The system must be scalable, maintainable, and testable, driven by a flexible, decoupled configuration.

**Core Philosophy:** The system is composed of two primary types of agents:
1.  **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code). They inherit from `BaseSpecialist`.
2.  **Orchestrators:** High-level components that manage a workflow by compiling a `LangGraph` instance and wiring together the necessary Specialists.

## 2.0 ARCHITECTURAL BLUEPRINT

The system is composed of the following layers and components.

### 2.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 2.2 Configuration (`config.yaml`): The System Blueprint
*   **Role:** The single source of truth for the system's structure.
*   **Function:** Defines all models, providers, and specialists, and declaratively "wires" them together. The application code is a generic engine that interprets this configuration at runtime.

### 2.3 The Adapter Factory Pattern
*   **Role:** Centralized component instantiation.
*   **Implementation:** The `AdapterFactory` reads the `config.yaml` to create and configure the correct LLM adapter for a given specialist.
*   **Principle:** Specialists request an adapter by name; they do not know the details of its creation. This decouples business logic from infrastructure.

### 2.4 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist`. Must implement the `execute(state: GraphState) -> Dict[str, Any]` method.
*   **Function:** A Specialist performs a single atomic task, usually by creating a `StandardizedLLMRequest` and passing it to its configured LLM adapter.

## 3.0 FILE & NAMING SCHEMA (MANDATORY)

### 3.1 Directory Structure
.
|-- app/
|   |-- config.yaml      # The central configuration file
|   |-- docs/
|   |   `-- DEVELOPERS_GUIDE.md
|   |-- prompts/
|   |   `-- ... (specialist prompts) ...
|   `-- src/
|       |-- graph/
|       |-- llm/           # Adapter abstractions, implementations, and factory
|       |-- specialists/   # Core agentic business logic
|       |-- utils/         # Shared utilities (config/prompt loaders)
|       |-- workflow/      # High-level workflow orchestration (ChiefOfStaff)
|       `-- main.py
|
|-- .env
`-- run.sh

### 3.2 Naming Convention
*   **Specialist Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains (e.g., `FileSpecialist` in `file_specialist.py`).
*   **Prompt Rule:** A prompt file in `app/prompts/` must be named according to the `prompt_file` key in `config.yaml`. This allows for model-specific prompt variations (e.g., `systems_architect_prompt_gguf.md`).

## 4.0 DEVELOPMENT PROTOCOLS

### 4.1 Protocol A: Creating a Standard Specialist

1.  **Define Prompt Contract:** Create a new file in `app/prompts/`.
2.  **Define Configuration:** Open `app/config.yaml` and add a new entry under the `specialists` key. Define its `model`, `provider`, and `prompt_file`.
3.  **Implement Specialist Logic:** Create a new file in `src/specialists/`. Use the following template:
    ```python
    from .base import BaseSpecialist
    from ..llm.adapter import StandardizedLLMRequest
    from langchain_core.messages import HumanMessage

    class NewSpecialist(BaseSpecialist):
        def __init__(self):
            # The specialist is identified by its class name in snake_case.
            super().__init__(specialist_name="new_specialist")

        def execute(self, state: dict) -> dict:
            user_input = state["messages"][-1].content

            # 1. Create a standardized request stating your intent.
            request = StandardizedLLMRequest(
                messages=[HumanMessage(content=user_input)]
                # Optionally add an output_schema for enforced JSON
                # output_schema={...}
            )

            # 2. Invoke the adapter configured for this specialist.
            response_data = self.llm_adapter.invoke(request)

            # 3. Process the structured response.
            # ... your logic here ...
            return {"some_new_key": response_data}
    ```
4.  **Integrate into Graph:** Add your new specialist to the `ChiefOfStaff` graph in `src/workflow/chief_of_staff.py`.

## 5.0 CONFIGURATION

### 5.1 Primary Configuration (`config.yaml`)
The system is primarily configured via `app/config.yaml`. This file defines the relationships between models, providers, and specialists. See the file for detailed examples.

### 5.2 Secrets & Connection Strings (`.env`)
The `.env` file is used for secrets and environment-specific connection details.
*   `GOOGLE_API_KEY`: **Required for Gemini.** Your API key for the Google AI platform.
*   `LMSTUDIO_BASE_URL`: **Required for LM Studio.** The base URL for your local LM Studio server (e.g., `http://localhost:1234/v1`).

## 6.0 Data Contracts
*(This section remains the same as the previously generated version)
