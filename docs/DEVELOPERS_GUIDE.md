# System Architecture & Developer's Guide
# Version: 2.5
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system. It is designed to be parsed by both human developers and autonomous AI agents.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

**Open Core Model:** This project is the "core" in an open core model. It provides generic, foundational capabilities under a permissive MIT license. Specialized, proprietary features (e.g., specific product integrations, complex UIs, opinionated agent personas) are intended to be built in separate, private projects that use this scaffold as a dependency or starting point.

**Core Philosophy:** The system is composed of two primary types of agents:
1.  **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code). They inherit from `BaseSpecialist`.
2.  **Orchestrators:** High-level components that manage a workflow by compiling a `LangGraph` instance and wiring together the necessary Specialists.

## 2.0 Getting Started

Follow these steps to set up and run the project.

### 2.1 Prerequisites
*   Python 3.10+
*   Git

### 2.2 Installation

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

### 2.3 Configuration

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

### 2.4 Running the Application

Use the provided scripts in the project root to run the application.

These scripts will start the FastAPI web server using Uvicorn. You can access the API at `http://127.0.0.1:8000` and view the interactive documentation (Swagger UI) at `http://127.0.0.1:8000/docs`.

On **Linux/macOS**:
```sh
./scripts/server.sh start
```
On **Windows**:
```bat
.\scripts\server.bat start
```

### 2.5 Running Tests

To ensure the system is functioning correctly, run the full suite of unit tests using `pytest`.

```sh
pytest
```

### 2.6 Verifying End-to-End Functionality

To quickly confirm that the entire system is wired correctly (server starts, API responds, and a basic agent workflow completes), you can run the verification script. This is a great sanity check to run after making significant changes.

On **Linux/macOS**:
```sh
./scripts/verify.sh
```

On **Windows** (requires PowerShell):
```powershell
.\scripts\verify.ps1
```

These scripts will automatically start the server, run a test prompt via the CLI, report success or failure, and then shut down the server.


### 2.7 Running via CLI

Once the FastAPI server is running, you can interact with it from the command line using the provided `cli.py` script. This is the recommended way to perform quick tests and script interactions without using a full API client.

1.  **Ensure the server is running in one terminal:**
    *   On **Linux/macOS**: `./scripts/server.sh start`
    *   On **Windows**: `.\scripts\server.bat start`

2.  **In a separate terminal, run the CLI:**
    Use the provided convenience script for your operating system.
    *   On **Linux/macOS**:
        ```sh
        ./scripts/cli.sh "Your prompt for the agent goes here."
        ```
    *   On **Windows**:
        ```bat
        .\scripts\cli.bat "Your prompt for the agent goes here."
        ```
    For example:
    ```sh
    ./scripts/cli.sh "Read the DEVELOPERS_GUIDE.md and summarize its main sections."
    ```
    The CLI will send the prompt to the `/invoke` endpoint and print the final JSON response from the agentic system.

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
*   **Contract:**
    *   Must inherit from `src.specialists.base.BaseSpecialist`.
    *   Must implement the `_execute_logic(self, state: dict) -> Dict[str, Any]` method.
    *   The public `execute` method is defined in the base class and provides a template with logging and error handling. You should not override it unless you have a specific reason.
*   **Function:** A Specialist performs a single atomic task, usually by creating a `StandardizedLLMRequest` and passing it to its configured LLM adapter.

**LLM-Optional Specialists:**
The system now supports specialists that do not require an associated Large Language Model (LLM). These are typically procedural specialists that perform deterministic tasks without needing AI inference. To define an LLM-optional specialist, simply omit the `model` and `provider` fields in its configuration within `config.yaml`. The `AdapterFactory` will automatically handle this by providing a `None` LLM adapter to such specialists. This allows for greater flexibility and efficiency by avoiding unnecessary LLM calls for purely procedural tasks.

### 3.5 Schema Enforcement Strategy

As outlined in the `PROPOSAL_ Schema-Enforced LLM Output Contracts.md` ADR, the system uses a "hard contract" approach to ensure LLMs produce reliable, structured JSON output. This is implemented via a progressive enhancement strategy in the LLM adapters.

*   **MIME Type Enforcement (e.g., Gemini):** For providers like Google Gemini, the adapter leverages the `response_mime_type` API parameter. When a specialist requests a Pydantic schema, the `GeminiAdapter` sets this parameter to `application/json`. This forces the model to generate a syntactically correct JSON string, while the system prompt guides the content and structure of that JSON.

*   **Full Schema Enforcement (e.g., LM Studio, OpenAI-compatible):** For providers that support it, the adapter can go a step further. The `LMStudioAdapter`, for example, can take a Pydantic model, convert it into a formal JSON Schema, and pass that schema directly to the API. This enforces not only the JSON format but also the specific fields, types, and structure of the output, offering the highest level of reliability.

This dual approach allows the system to use the strongest enforcement mechanism available for any given provider, with a graceful fallback to prompt-guided generation if a provider supports neither.

### 3.6 Application Internals: Separation of Concerns

The `app/src` directory is organized to enforce a clear separation of concerns, making the system more modular and maintainable.

*   `specialists/`: This is the core directory for the agentic workforce. Each file defines a `BaseSpecialist` subclass that encapsulates a specific skill or task. For example, `file_specialist.py` handles file operations, while `web_builder.py` might generate HTML.

*   `workflow/`: This directory contains the high-level orchestration logic. It defines how the different specialists work together to achieve a larger goal. The `ChiefOfStaff` class, for instance, compiles the `LangGraph`, defining the flow of control and state between specialists.

*   `llm/`: This directory abstracts away the complexities of interacting with different Large Language Models. The `adapter` and `factory` modules provide a standardized interface for specialists to make requests to LLMs without needing to know the specific implementation details of each provider (e.g., OpenAI, Google GenAI).

*   `graph/`: This directory defines the structure of the shared state that is passed between all nodes in the LangGraph. The `state.py` file defines the `GraphState` TypedDict, ensuring that all specialists have a consistent view of the application's state.

*   `utils/`: This directory contains shared utility functions and classes that are used across the application. For example, the `config_loader.py` is responsible for loading the `config.yaml` file, and `prompt_loader.py` loads the prompt templates for the specialists.

## 4.0 How to Extend the System

### 4.1 Adding New Specialists

The primary way to extend the system's capabilities is by adding new specialists. This can be done by creating a new standard specialist from scratch or by wrapping an existing, external agent.

For a detailed, step-by-step tutorial on both of these processes, please refer to the **Creating a New Specialist** guide.

### 4.2 Managing Dependencies

This project uses `pyproject.toml` as the single source of truth for dependencies and `pip-tools` to generate pinned `requirements.txt` files for reproducible installations.

**To add or update a dependency:**

1.  Edit the `[project.dependencies]` or `[project.optional-dependencies.dev]` sections in `pyproject.toml`.
2.  Run the sync script to regenerate the lock files:
    *   On Linux/macOS: `./scripts/sync-reqs.sh`
    *   On Windows: `.\scripts\sync-reqs.bat`
3.  Commit the changes to `pyproject.toml` **and** the generated `requirements.txt` / `requirements-dev.txt` files to version control.

### 4.3 Packaging

This project is structured as an installable Python package. The `pyproject.toml` file defines the package metadata, and the `app` directory contains the source code. This allows for clean dependency management and distribution.

## 5.0 Project Structure Reference

### 5.1 Directory Structure
```
langgraph-agentic-scaffold/
|-- .env.example         # Example environment file for secrets
|-- .gitignore           # Files and directories ignored by Git
|-- LICENSE              # Project license
|-- README.md            # Main project README
|-- config.yaml.example  # Example application configuration
|-- pyproject.toml       # Project definition and dependencies
|-- requirements-dev.txt # Pinned development dependencies
|-- requirements.txt     # Pinned production dependencies
|-- app/
|   |-- prompts/         # Prompt templates for specialists
|   |-- src/             # Main application source code
|   |   |-- api.py           # FastAPI application entry point
|   |   |-- cli.py           # Command-line interface script
|   |   |-- specialists/     # Specialist agent implementations
|   |   |-- workflow/        # LangGraph orchestration logic
|   |   `-- ... (llm, graph, utils, etc.)
|   `-- tests/             # Unit and integration tests
|-- docs/                # All project documentation
|   |-- DEVELOPERS_GUIDE.md
|   |-- CREATING_A_NEW_SPECIALIST.md
|   `-- adr/               # Architecture Decision Records
|-- external/            # For third-party code (e.g., wrapped agents)
|   `-- .gitkeep         # Keeps the directory in Git history
`-- scripts/             # Helper scripts for development
    |-- server.sh          # Server management (start, stop) for Linux/macOS
    |-- server.bat         # Server management for Windows
    `-- ... (verify, cli, sync-reqs scripts)
```

### 5.2 Naming Convention
*   **Specialist Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains (e.g., `FileSpecialist` in `file_specialist.py`).
*   **Prompt Rule:** A prompt file in `app/prompts/` must be named according to the `prompt_file` key in `config.yaml`. This allows for model-specific prompt variations (e.g., `systems_architect_prompt_gguf.md`).
