# System Architecture & Developer's Guide
# Version: 2.5
# Status: ACTIVE

This document provides all the necessary information to understand, run, test, and extend the agentic system. It is designed to be parsed by both human developers and autonomous AI agents.

## 1.0 Mission & Philosophy

**Mission:** To provide the best possible open-source starting point for building any LangGraph-based agentic system. The scaffold focuses on modularity, extensibility, and architectural best practices.

**Open Core Model:** This project is the "core" in an open core model. It provides generic, foundational capabilities under a permissive MIT license. Specialized, proprietary features (e.g., specific product integrations, complex UIs, opinionated agent personas) are intended to be built in separate, private projects that use this scaffold as a dependency or starting point.

**Core Philosophy:** The system is composed of several agent types with a clear separation of concerns:
1.  **Specialists (`BaseSpecialist`):** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code).
2.  **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph. It uses its LLM to analyze the conversation state and decides which Specialist should run next, updating the `GraphState` with its choice.
3.  **Structural Orchestrator (`ChiefOfStaff`):** A high-level system component responsible for building the `LangGraph` instance, loading all Specialists from the configuration, and enforcing global rules (like max turns or error handling). It reads the decision made by the `RouterSpecialist` to direct the flow of the graph.

## 2.0 Getting Started

Follow these steps to set up and run the project.

### 2.1 Prerequisites
*   Python 3.10+
*   Git

### 2.2 Installation

To set up your development environment, run the appropriate installation script for your operating system from the project root:

*   On **Linux/macOS**:
    `./scripts/install.sh`
*   On **Windows**:
    `.\scripts\install.bat`

These scripts will:
*   Clone the repository (if not already cloned).
*   Create and activate a Python virtual environment.
*   Install all necessary Python dependencies.
*   Copy example configuration files (`.env.example` to `.env`, `config.yaml.example` to `config.yaml`).
*   Check for the `jq` command-line JSON processor (required for verification scripts) and provide installation instructions if missing.
*   For Windows, provide a note about PowerShell execution policy if running PowerShell scripts.

After running the installation script, remember to edit `.env` with your API keys and `config.yaml` to define your agent setup.

### 2.3 Configuration

(This section is now largely handled by the install scripts, but keeping it for reference if manual config is needed)

1.  **Environment Secrets:** In the project root, copy `.env.example` to a new file named `.env`. This file stores secrets and is safely ignored by Git.
    `cp .env.example .env`
    The `scripts/server.py` controller is responsible for loading this `.env` file into the process environment before launching the Uvicorn server. The application code itself assumes these variables are present and does not load the file. This creates a clean separation of concerns between the application and its execution environment.

    Then, edit `.env` with your API keys. The log levels for the application and its components are now controlled exclusively by `log_config.yaml`.
2.  **Application Configuration:** In the project root, copy `config.yaml.example` to a new file named `config.yaml`. This file defines the agentic system's structure and can be modified without tracking changes in Git if desired.
    `cp config.yaml.example config.yaml`

### 2.4 Running the Application

Use the provided scripts in the project root to run the application.

On **Linux/macOS**:
`./scripts/server.sh start`
On **Windows**:
`.\scripts\server.bat start`

### 2.5 Running Tests

To ensure the system is functioning correctly, run the full suite of unit tests using `pytest`.

`pytest`

### 2.6 Verifying End-to-End Functionality

To quickly confirm that the entire system is wired correctly (server starts, API responds, and a basic agent workflow completes), you can run the verification script. This is a great sanity check to run after making significant changes.

On **Linux/macOS**:
`./scripts/verify.sh`

On **Windows** (requires PowerShell):
`.\scripts\verify.ps1`

These scripts will automatically start the server, run a test prompt via the CLI, report success or failure, and then shut down the server.


### 2.7 Running via CLI

Once the FastAPI server is running, you can interact with it from the command line using the provided `cli.py` script. This is the recommended way to perform quick tests and script interactions without using a full API client.

1.  **Ensure the server is running in one terminal:**
    *   On **Linux/macOS**: `./scripts/server.sh start`
    *   On **Windows**: `.\scripts\server.bat start`

2.  **In a separate terminal, run the CLI:**
    Use the provided convenience script for your operating system.
    *   On **Linux/macOS**:
        `./scripts/cli.sh "Your prompt for the agent goes here."`
    *   On **Windows**:
        `.\scripts\cli.bat "Your prompt for the agent goes here."`
    For example:
    `.\scripts\cli.bat "Read the DEVELOPERS_GUIDE.md and summarize its main sections."`
    The CLI will send the prompt to the `/invoke` endpoint and print the final JSON response from the agentic system.

## 3.0 System Architecture

The system is composed of several layers and components, governed by clear configuration philosophy.

### 3.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 3.2 Configuration Philosophy: The Three Layers

The scaffold uses a three-layer configuration model to cleanly separate concerns. Understanding this is critical to using the system effectively and securely.

1.  **Layer 1: The System Blueprint (`config.yaml`)**
    *   **Purpose:** Defines the complete set of capabilities for the application. It lists all possible LLM providers and all available specialists.
    *   **Audience:** The Developer.
    *   **Source Control:** **This file SHOULD be committed to Git.** It is part of the application's source code, ensuring that every developer works from the same architectural blueprint.

2.  **Layer 2: User Settings (`user_settings.yaml`)**
    *   **Purpose:** Allows a user to make choices from the options defined in the blueprint. Its primary role is to bind specialists to specific LLM configurations.
    *   **Audience:** The End-User (or the developer during testing).
    *   **Source Control:** **This file should NOT be committed to Git.** It is specific to a local environment and is listed in `.gitignore`.

3.  **Layer 3: Secrets (`.env`)**
    *   **Purpose:** Holds secrets like API keys.
    *   **Audience:** The machine's environment / the developer setting up an instance.
    *   **Source Control:** **This file must NEVER be committed to Git.**

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
The system supports specialists that do not require an LLM. These are typically procedural specialists that perform deterministic tasks. To define one, set `type: "procedural"` in its `config.yaml` entry. The `AdapterFactory` will not create an LLM adapter for specialists of this type, which allows for greater flexibility and efficiency by avoiding unnecessary LLM calls for purely procedural tasks.

### 3.5 Schema Enforcement Strategy

As outlined in the `PROPOSAL_ Schema-Enforced LLM Output Contracts.md` ADR, the system uses a "hard contract" approach to ensure LLMs produce reliable, structured JSON output. This is implemented via a progressive enhancement strategy in the LLM adapters.

*   **MIME Type Enforcement (e.g., Gemini):** For providers like Google Gemini, the `GeminiAdapter` leverages the `response_mime_type` API parameter. This is a "light contract" that forces the model to generate a syntactically correct JSON string, while the system prompt guides the content and structure of that JSON.

*   **Full Schema Enforcement (e.g., LM Studio, OpenAI-compatible):** For providers that support it, the `LMStudioAdapter` can take a Pydantic model, convert it into a formal JSON Schema, and pass that schema directly to the API using the `response_format` parameter. This enforces not only the JSON format but also the specific fields, types, and structure of the output, offering the highest level of reliability.

This dual approach allows the system to use the strongest enforcement mechanism available for any given provider, with a graceful fallback to prompt-guided generation if a provider supports neither.

### 3.6 Application Internals: Separation of Concerns

The `app/src` directory is organized to enforce a clear separation of concerns, making the system more modular and maintainable.

*   `specialists/`: This is the core directory for the agentic workforce. Each file defines a `BaseSpecialist` subclass that encapsulates a specific skill or task. For example, `file_specialist.py` handles file operations, while `web_builder.py` might generate HTML.

*   `workflow/`: This directory contains the high-level orchestration logic. It defines how the different specialists work together to achieve a larger goal. The `ChiefOfStaff` class, for instance, compiles the `LangGraph`, defining the flow of control and state between specialists.

*   `llm/`: This directory abstracts away the complexities of interacting with different Large Language Models. The `adapter` and `factory` modules provide a standardized interface for specialists to make requests to LLMs without needing to know the specific implementation details of each provider (e.g., OpenAI, Google GenAI).

*   `graph/`: This directory defines the structure of the shared state that is passed between all nodes in the LangGraph. The `state.py` file defines the `GraphState` TypedDict, ensuring that all specialists have a consistent view of the application's state.

*   `utils/`: This directory contains shared utility functions and classes that are used across the application. For example, the `config_loader.py` is responsible for loading the `config.yaml` file, and `prompt_loader.py` loads the prompt templates for the specialists.

### 3.7 Agentic Robustness Patterns

This scaffold implements several advanced patterns to move beyond simple instruction-following and create a more robust, resilient agentic system.

*   **Two-Stage Semantic Routing:** The system uses a sophisticated routing mechanism to improve efficiency and accuracy.
    *   **Stage 1: Recommendation (`PromptTriageSpecialist`):** The workflow begins with the Triage specialist, which acts as a "Semantic Recommender." It analyzes the user's initial prompt against the descriptions of all available specialists and outputs a `recommended_specialists` list into the `GraphState`.
    *   **Stage 2: Dispatch (`RouterSpecialist`):** The Router uses the `recommended_specialists` list to make an intelligent decision.
        *   If the list contains exactly one specialist, it's treated as a **deterministic handoff**. The Router bypasses its own LLM call and routes directly to that specialist, increasing speed and reliability.
        *   If the list contains multiple specialists, the Router uses this list to create a filtered, contextual menu of choices for its LLM call. This simplifies the LLM's task, making it cheaper and more accurate.
        *   If the list is **absent** (i.e., not provided by a previous step), the Router falls back to using the full list of all available specialists.
        *   If the list is **empty**, this indicates that the Triage specialist found no relevant specialists, and the workflow will end gracefully.

*   **Self-Correction via Recommendations:** The recommendation pattern is also used for self-correction. If a specialist is called without its preconditions being met (e.g., `TextAnalysisSpecialist` is called before a file has been read), it returns a helpful `AIMessage` explaining the problem and a `recommended_specialists` list containing the name of the specialist that can resolve the issue (e.g., `["file_specialist"]`). The Router then uses this recommendation to correct the workflow.

*   **Programmatic Task Completion:** Similar to routing, determining when a task is truly "done" can be ambiguous for an LLM. To solve this, terminal specialists (those that produce a final answer, like `TextAnalysisSpecialist`) can set a `task_is_complete: True` flag in the state they return. The `RouterSpecialist` checks for this flag at the beginning of its turn and, if present, immediately routes to `END` without consulting the LLM. This provides a deterministic signal that the user's goal has been met.

*   **Atomic State Updates:** The LangGraph is configured to *add* new messages to the conversation history. Therefore, it is critical that specialists only return the *new* messages or state changes they are responsible for (the "delta"). They should not return the entire message history they received. Adhering to this pattern prevents the conversation history from growing exponentially, which would quickly exhaust the context window of any LLM.

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

This project is structured as an installable Python package. The `pyproject.toml` file defines the package metadata, and the `app` directory contains the source code. It allows for clean dependency management and distribution.

## 5.0 Project Structure Reference

### 5.1 Directory Structure Overview

This section provides a high-level overview of the repository's layout. For a comprehensive, file-by-file explanation of the project's structure and the purpose of each component, please see the **Project Structure Deep Dive** in `PROJECT_STRUCTURE.md`.

*   `app/`: The main Python package containing all source code (`src/`), tests (`tests/`), and prompts (`prompts/`).
*   `docs/`: All project documentation, including this guide, tutorials, and Architecture Decision Records (ADRs).
*   `scripts/`: Helper scripts for common development tasks like running the server, managing dependencies, and verification.
*   `external/`: A directory for integrating third-party agent code.
*   **Root files:** Configuration (`config.yaml.example`, `user_settings.yaml.example`), dependencies (`pyproject.toml`), and other project-level files.

### 5.2 Naming Convention
*   **Specialist Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains (e.g., `FileSpecialist` in `file_specialist.py`).
*   **Prompt Rule:** A prompt file in `app/prompts/` must be named according to the `prompt_file` key in `config.yaml`. This allows for model-specific prompt variations (e.g., `systems_architect_prompt_gguf.md`).