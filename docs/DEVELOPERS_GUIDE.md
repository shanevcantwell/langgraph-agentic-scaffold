# SpecialistHub: System Architecture & Developer's Guide
# Version: 2.3
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the SpecialistHub agentic system. It is designed to be parsed by both human developers and autonomous AI agents.

## 1.0 Getting Started

Follow these steps to set up and run the project.

### 1.1 Prerequisites
*   Python 3.10+
*   Git

### 1.2 Installation

1.  **Clone the repository:**
    ```sh
    git clone <repository-url>
    cd langgraph-agentic-scaffold
    ```

2.  **Create and activate a virtual environment.**

    For **Linux/macOS** (using the `.venv_agents` directory):
    ```sh
    python3 -m venv .venv_agents
    source ./.venv_agents/bin/activate
    ```
    For **Windows** (using the `.venv_agents_windows` directory):
    ```bat
    python -m venv .venv_agents_windows
    .\.venv_agents_windows\Scripts\activate
    ```

3.  **Install dependencies:**
    To set up a development environment, install all production and development dependencies, including tools for testing, formatting, and dependency management.
    ```sh
    pip install -r requirements-dev.txt
    ```
    This command ensures you have all the tools needed to contribute to the project.

### 1.3 Configuration

1.  **Environment Secrets:** In the project root, copy `.env.example` to a new file named `.env`. This file stores secrets and is safely ignored by Git.
    ```sh
    cp .env.example .env
    ```
    Then, edit `.env` with your API keys. You can also set the console log level for the API server by adding the following line:
    ```
    LOG_LEVEL=DEBUG
    ```
    Valid levels are `DEBUG`, `INFO`, `WARNING`, and `ERROR`. If not set, the server defaults to `INFO`.

2.  **Application Configuration:** In the project root, copy `config.yaml.example` to a new file named `config.yaml`. This file defines the agentic system's structure and can be modified without tracking changes in Git if desired.
    ```sh
    cp config.yaml.example config.yaml
    ```

### 1.4 Running the Application

Use the provided scripts in the project root to run the application.

These scripts will start the FastAPI web server using Uvicorn. You can access the API at `http://127.0.0.1:8000` and view the interactive documentation (Swagger UI) at `http://127.0.0.1:8000/docs`.

On **Linux/macOS**:
```sh
./run.sh start
```
On **Windows**:
```bat
.\windows_run.bat
```

### 1.5 Running Tests

To ensure the system is functioning correctly, run the full suite of unit tests using `pytest`.

```sh
pytest
```

### 1.6 Running via CLI

Once the FastAPI server is running, you can interact with it from the command line using the provided `cli.py` script. This is the recommended way to perform quick tests and script interactions without using a full API client.

1.  **Ensure the server is running in one terminal:**
    *   On **Linux/macOS**: `./run.sh start`
    *   On **Windows**: `.\windows_run.bat`

2.  **In a separate terminal, run the CLI:**
    ```sh
    python app/src/cli.py "Your prompt for the agent goes here."
    ```
    For example:
    ```sh
    python app/src/cli.py "Read the DEVELOPERS_GUIDE.md and summarize its main sections."
    ```
    The CLI will send the prompt to the `/invoke` endpoint and print the final JSON response from the agentic system.

## 2.0 Mission & Philosophy

**Mission:** To construct a multi-agent system composed of modular, single-responsibility "Specialists." The system must be scalable, maintainable, and testable, driven by a flexible, decoupled configuration.

**Core Philosophy:** The system is composed of two primary types of agents:
1.  **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code). They inherit from `BaseSpecialist`.
2.  **Orchestrators:** High-level components that manage a workflow by compiling a `LangGraph` instance and wiring together the necessary Specialists.

## 3.0 System Architecture

The system is composed of the following layers and components.

### 3.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 3.2 Configuration (`config.yaml`): The System Blueprint
*   **Role:** The single source of truth for the system's structure.
*   **Function:** Defines all models, providers, and specialists, and declaratively "wires" them together. The application code is a generic engine that interprets this configuration at runtime.

### 3.3 The Adapter Factory Pattern
*   **Role:** Centralized component instantiation.
*   **Implementation:** The `AdapterFactory` reads the `config.yaml` to create and configure the correct LLM adapter for a given specialist.
*   **Principle:** Specialists request an adapter by name; they do not know the details of its creation. This decouples business logic from infrastructure.

### 3.4 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist`. Must implement the `execute(state: GraphState) -> Dict[str, Any]` method.
*   **Function:** A Specialist performs a single atomic task, usually by creating a `StandardizedLLMRequest` and passing it to its configured LLM adapter.

**LLM-Optional Specialists:**
The system now supports specialists that do not require an associated Large Language Model (LLM). These are typically procedural specialists that perform deterministic tasks without needing AI inference. To define an LLM-optional specialist, simply omit the `model` and `provider` fields in its configuration within `config.yaml`. The `AdapterFactory` will automatically handle this by providing a `None` LLM adapter to such specialists. This allows for greater flexibility and efficiency by avoiding unnecessary LLM calls for purely procedural tasks.

## 4.0 Project Structure & Naming

### 4.1 Directory Structure
```
.
|-- .env                 # Local environment secrets (DO NOT COMMIT)
|-- .env.example         # Example environment file
|-- config.yaml          # Local configuration (can be gitignored)
|-- config.yaml.example  # Example configuration file
|-- data_processor_specialist.py # Stub for procedural processing
|-- requirements-dev.txt # Development dependencies
|-- run.sh               # Execution script for Linux/macOS
|-- windows_run.bat      # Execution script for Windows
|-- docs/                # All project documentation
|   |-- DEVELOPERS_GUIDE.md
|   |-- MANIFEST.json
|   `-- ... (proposals, etc.)
`-- app/
    |-- prompts/         # Prompt templates for specialists
    |-- src/
    |   |-- api.py           # FastAPI application entry point
    |   |-- cli.py           # Command-line interface script
    |   |-- enums.py         # System-wide enumerations
    |   |-- graph/           # LangGraph state and nodes
    |   |-- llm/             # LLM abstraction layer
    |   |-- specialists/     # Specialist agent implementations
    |   |-- utils/           # Shared utility functions
    |   `-- workflow/        # LangGraph orchestration logic
    `-- tests/
```

### 4.2 Naming Convention
*   **Specialist Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains (e.g., `FileSpecialist` in `file_specialist.py`).
*   **Prompt Rule:** A prompt file in `app/prompts/` must be named according to the `prompt_file` key in `config.yaml`. This allows for model-specific prompt variations (e.g., `systems_architect_prompt_gguf.md`).

## 5.0 Application Internals: Separation of Concerns

The `app/src` directory is organized to enforce a clear separation of concerns, making the system more modular and maintainable.

*   `specialists/`: This is the core directory for the agentic workforce. Each file defines a `BaseSpecialist` subclass that encapsulates a specific skill or task. For example, `file_specialist.py` handles file operations, while `web_builder.py` might generate HTML.

*   `workflow/`: This directory contains the high-level orchestration logic. It defines how the different specialists work together to achieve a larger goal. The `ChiefOfStaff` class, for instance, compiles the `LangGraph`, defining the flow of control and state between specialists.

*   `llm/`: This directory abstracts away the complexities of interacting with different Large Language Models. The `adapter` and `factory` modules provide a standardized interface for specialists to make requests to LLMs without needing to know the specific implementation details of each provider (e.g., OpenAI, Google GenAI).

*   `graph/`: This directory defines the structure of the shared state that is passed between all nodes in the LangGraph. The `state.py` file defines the `GraphState` TypedDict, ensuring that all specialists have a consistent view of the application's state.

*   `utils/`: This directory contains shared utility functions and classes that are used across the application. For example, the `config_loader.py` is responsible for loading the `config.yaml` file, and `prompt_loader.py` loads the prompt templates for the specialists.

## 6.0 Development Protocols

### 6.1 Protocol A: Creating a Standard Specialist

1.  **Define Prompt Contract:** Create a new prompt file in `app/prompts/`.
2.  **Define Configuration:** Open `config.yaml` and add a new entry under the `specialists` key. Define its `model`, `provider`, and `prompt_file`.
3.  **Implement Specialist Logic:** Create a new file in `src/specialists/`. Use the following template:
    ```python
    from .base import BaseSpecialist
    from ..llm.adapter import StandardizedLLMRequest
    from langchain_core.messages import AIMessage, HumanMessage

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
            # Your logic here to process response_data.
            # For example, add the AI's response back to the message history.
            ai_message = AIMessage(content=str(response_data))

            return {"messages": state["messages"] + [ai_message]}
    ```

### 6.2 Protocol B: Managing Dependencies

This project uses `pyproject.toml` as the single source of truth for dependencies and `pip-tools` to generate pinned `requirements.txt` files for reproducible installations.

**To add or update a dependency:**

1.  Edit the `[project.dependencies]` or `[project.optional-dependencies.dev]` sections in `pyproject.toml`.
2.  Run the sync script to regenerate the lock files:
    *   On Linux/macOS: `./scripts/sync-reqs.sh`
    *   On Windows: `.\scripts\sync-reqs.bat`
3.  Commit the changes to `pyproject.toml` **and** the generated `requirements.txt` / `requirements-dev.txt` files to version control.

### 6.3 Packaging

This project is structured as an installable Python package. The `pyproject.toml` file defines the package metadata, and the `app` directory contains the source code. This allows for clean dependency management and distribution.