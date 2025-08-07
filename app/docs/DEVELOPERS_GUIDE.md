# [SYSTEM BOOTSTRAP] DEVELOPERS_GUIDE.md
# Project: SpecialistHub
# Version: 1.1
# Status: ACTIVE

## 1.0 CORE DIRECTIVE: MISSION & PHILOSOPHY

**Mission:** To construct a multi-agent system composed of modular, single-responsibility "Specialists." The system must be scalable, maintainable, and testable.

**Core Philosophy:** Specialists are treated as "intelligent objects" or "functional components." They are predictable processors within a larger computational graph. The system prioritizes reliability and machine-to-machine communication over human-like interaction for its internal operations.

## 2.0 ARCHITECTURAL BLUEPRINT

The system is composed of the following layers and components.

### 2.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes based on their output.
*   **Execution Model:** The graph is designed as a **cyclical loop**. Control typically returns to the `RouterSpecialist` after a task, allowing for multi-step execution.

### 2.2 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist`. Must implement the `execute(state: GraphState) -> Dict[str, Any]` method.
*   **Constraint:** A Specialist must have a single, well-defined responsibility. They operate on the shared `GraphState` and utilize shared resources provided by factories.

### 2.3 The Router/Supervisor: The Central Dispatcher
*   **Role:** Orchestrator / Decision Engine.
*   **Implementation:** A dedicated Specialist (`RouterSpecialist`).
*   **Function:** To receive the current `GraphState` and output a machine-readable JSON directive indicating the next Specialist node to execute. It is also responsible for terminating the loop by routing to the special `END` state when a task is complete.

### 2.4 Shared Resources: The Singleton Factory Pattern
*   **Principle:** To conserve resources and ensure consistency, critical services like LLM clients are managed as **Singletons**.
*   **Implementation:** The `LLMClientFactory` maintains a registry of client instances. It will create a client for a specific provider only once, and return that same instance for all subsequent requests. **Specialists do not create their own clients.**

### 2.5 LLM Interaction Protocol: `json<-->json`
This is a non-negotiable protocol for all internal system communication.
*   **Type:** Functional / Transactional.
*   **Input:** LLM calls must be provided with a structured prompt that includes a strict JSON schema for the desired output.
*   **Output:** The LLM's response **must** be a valid JSON string, with no extraneous conversational text.

## 3.0 FILE & NAMING SCHEMA (MANDATORY)

Adherence to this structure is required for system integrity and automated parsing.

### 3.1 Directory Structure
src/ ├── graph/ │ └── state.py # Schema definition for GraphState TypedDict. ├── llm/ │ ├── clients.py # LLM client implementations (BaseLLMClient, etc.). │ └── factory.py # Singleton LLMClientFactory for client instantiation. ├── prompts/ │ └── *.prompt # System prompts as discrete text files. ├── specialists/ │ ├── base.py # The BaseSpecialist abstract base class. │ └── *.py # Concrete specialist implementations. └── utils/ └── prompt_loader.py # Standardized utility for loading from src/prompts/.



Copy block


### 3.2 Naming Convention
*   **Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains.
*   **Example:** The class `FileSpecialist` must reside in the file `file_specialist.py`.

## 4.0 PROTOCOL: CREATING A NEW SPECIALIST

Execute the following sequence to provision a new Specialist.

### 4.1 Step 1: Define Prompt Contract
Create a new file in `src/prompts/`. The filename must be `{specialist_name}.prompt`. Define the system prompt here, including the required JSON output schema if it is a functional specialist.

### 4.2 Step 2: Implement Specialist Logic
Create a new file in `src/specialists/` following the naming convention. Use the standard template, ensuring the `execute` method correctly reads from and writes to the `GraphState`.

### 4.3 Step 3: Register Specialist in Graph
1.  **Update Router Prompt:** Modify `src/prompts/router_specialist.prompt` to include your new specialist as a valid routing destination in its list of tools/options.
2.  **Add Node to Graph:** In the main application file (e.g., `src/main.py`), import and instantiate your new specialist. Add it as a node to the `StatefulGraph` object.
3.  **Add Edge to Graph:** Add an edge from your new specialist's node **back to the `router_specialist` node**. This ensures the loop continues after your specialist runs.

## 5.0 CONFIGURATION: ENVIRONMENT VARIABLES

System configuration is managed exclusively via environment variables. (No change from v1.0)