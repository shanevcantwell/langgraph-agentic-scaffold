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

The project follows a structured layout to ensure a clear separation of concerns.

.
|-- app/
|   |-- docs/
|   |   `-- DEVELOPERS_GUIDE.md
|   |-- prompts/
|   |   `-- ... (specialist prompts) ...
|   `-- src/
|       |-- graph/         # LangGraph state, nodes, and graph compilation
|       |-- llm/           # LLM client implementations and factory
|       |-- specialists/   # Core agentic business logic
|       |-- utils/         # Shared utilities (e.g., prompt_loader)
|       |-- workflow/      # High-level workflow orchestration and service APIs
|       |   `-- runner.py
|       `-- main.py        # Main application entry point
|
|-- .env
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

## 5. Data Contracts

To ensure reliable, state-driven communication between specialists, the project uses standardized JSON schemas for artifacts passed in the `GraphState`. This section serves as the canonical reference for these schemas. Adherence to these contracts is mandatory for system stability.

### 5.1 Sequence Diagram JSON Schema

This schema is the standard format for representing sequence diagrams within the system. It is produced by the `SystemsArchitect` and consumed by specialists like the `WebBuilder`.

**Root Object:**

| Key            | Type              | Description                                                  |
| :------------- | :---------------- | :----------------------------------------------------------- |
| `diagram_type` | `string`          | The type of diagram. Must be `"sequence"`.                   |
| `title`        | `string`          | A concise and descriptive title for the diagram.             |
| `participants` | `array of objects` | A list of all participants in the diagram. See below.        |
| `flow`         | `array of objects` | The ordered sequence of interactions. See below.             |

**Participant Object:**

| Key    | Type     | Description                                                              |
| :----- | :------- | :----------------------------------------------------------------------- |
| `id`   | `string` | A short, lowercase, `snake_case` identifier (e.g., "user", "api_server"). |
| `name` | `string` | The full, display name of the participant (e.g., "User", "API Server").  |
| `type` | `string` | The type of participant. Must be either `"actor"` or `"participant"`.    |

**Flow Object:**

| Key        | Type      | Description                                                                  |
| :--------- | :-------- | :--------------------------------------------------------------------------- |
| `from`     | `string`  | The `id` of the originating participant.                                     |
| `to`       | `string`  | The `id` of the destination participant.                                     |
| `action`   | `string`  | A brief description of the action being performed.                           |
| `is_reply` | `boolean` | `false` for a request/action (solid line). `true` for a reply (dashed line). |

---

#### **Canonical Example**

```json
{
  "diagram_type": "sequence",
  "title": "User Login Flow",
  "participants": [
    {
      "id": "user",
      "name": "User",
      "type": "actor"
    },
    {
      "id": "webapp",
      "name": "Web Application",
      "type": "participant"
    },
    {
      "id": "api",
      "name": "API Server",
      "type": "participant"
    },
    {
      "id": "db",
      "name": "Database",
      "type": "participant"
    }
  ],
  "flow": [
    {
      "from": "user",
      "to": "webapp",
      "action": "Submit credentials",
      "is_reply": false
    },
    {
      "from": "webapp",
      "to": "api",
      "action": "Validate credentials",
      "is_reply": false
    },
    {
      "from": "api",
      "to": "db",
      "action": "Query for user",
      "is_reply": false
    },
    {
      "from": "db",
      "to": "api",
      "action": "Return user record",
      "is_reply": true
    },
    {
      "from": "api",
      "to": "webapp",
      "action": "Return JWT token",
      "is_reply": true
    },
    {
      "from": "webapp",
      "to": "user",
      "action": "Login successful",
      "is_reply": true
    }
  ]
}
