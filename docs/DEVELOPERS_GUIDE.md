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
3.  **Structural Orchestrator (`ChiefOfStaff`):** A high-level system component responsible for building the `LangGraph` instance, loading all Specialists from the configuration, and enforcing global rules (like detecting unproductive loops or handling errors). It reads the decision made by the `RouterSpecialist` to direct the flow of the graph.

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

These scripts will create a virtual environment, install dependencies, and copy example configuration files. After running the script, remember to edit `.env` with your API keys.

### 2.3 Configuration

The system uses a three-layer configuration model to cleanly separate concerns.

1.  **Layer 1: The System Blueprint (`config.yaml`)**: Defines the complete set of capabilities for the application. It lists all possible LLM providers and all available specialists. This file **SHOULD** be committed to Git.
2.  **Layer 2: User Settings (`user_settings.yaml`)**: Allows a user to make choices from the blueprint, primarily by binding specialists to specific LLM configurations. This file **should NOT** be committed to Git.
3.  **Layer 3: Secrets (`.env`)**: Holds secrets like API keys. This file **must NEVER** be committed to Git.

### 2.4 Running the Application

Use the provided scripts in the project root to run the application.

*   On **Linux/macOS**: `./scripts/server.sh start`
*   On **Windows**: `.\scripts\server.bat start`

### 2.5 Running Tests

To ensure the system is functioning correctly, run the full suite of unit tests using `pytest`.

`pytest`

### 2.6 Interacting via CLI

Once the FastAPI server is running, you can interact with it from a separate terminal using the provided `cli` script.

*   On **Linux/macOS**: `./scripts/cli.sh "Your prompt for the agent goes here."`
*   On **Windows**: `.\scripts\cli.bat "Your prompt for the agent goes here."`

## 3.0 System Architecture

### 3.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes.

### 3.2 The Adapter Factory Pattern
*   **Role:** Centralized component instantiation.
*   **Implementation:** The `AdapterFactory` reads the merged configuration to create and configure the correct LLM adapter for a given specialist.
*   **Principle:** Specialists request an adapter by name; they do not know the details of its creation. This decouples business logic from infrastructure.

### 3.3 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist` and implement the `_execute_logic` method.
*   **Function:** A Specialist performs a single atomic task, usually by creating a `StandardizedLLMRequest` and passing it to its configured LLM adapter.

**Procedural Specialists:**
The system supports specialists that execute deterministic code. This is ideal for simple tasks (like archiving) or for safely integrating external tools that may have their own internal logic (like `open-interpreter`). For a detailed walkthrough of the best-practice "Plan and Execute" pattern for tool integration, see the `How to Create a New Specialist` guide.

### 3.4 Schema Enforcement Strategy
The system uses a "hard contract" approach to ensure LLMs produce reliable, structured JSON output. This is implemented via a progressive enhancement strategy in the LLM adapters, using the strongest enforcement mechanism available for any given provider (e.g., `response_format` for OpenAI-compatible models, `response_mime_type` for Gemini).

### 3.5 Application Internals: Separation of Concerns
The `app/src` directory is organized to enforce modularity:
*   `specialists/`: The core agentic workforce. Each file defines a `BaseSpecialist` subclass.
*   `workflow/`: High-level orchestration logic, including the `ChiefOfStaff`.
*   `llm/`: Abstractions for interacting with different LLMs (`adapter`, `factory`).
*   `graph/`: Definition of the shared `GraphState`.
*   `utils/`: Shared utilities like the `ConfigLoader`.

### 3.6 Agentic Robustness Patterns

This scaffold implements several advanced patterns to create a more robust, resilient agentic system.

*   **Two-Stage Semantic Routing:**
    *   **Stage 1: Recommendation (`PromptTriageSpecialist`):** This specialist analyzes the user's initial prompt against the descriptions of all available specialists and outputs a `recommended_specialists` list.
    *   **Stage 2: Dispatch (`RouterSpecialist`):** The Router uses this list to make an intelligent decision. If the list contains one specialist, it performs a fast, deterministic handoff. If it contains multiple, it uses the list as a filtered menu for its LLM, improving accuracy and reducing cost.

*   **Self-Correction via Precondition Checks:** The system uses a centralized, declarative approach for self-correction. Instead of each specialist checking its own preconditions, the `ChiefOfStaff` does it automatically. By adding a `requires_artifacts: ["file_content"]` key to a specialist's configuration in `config.yaml`, you declare its dependencies. If this specialist is called before the required artifact exists in the `GraphState`, the `ChiefOfStaff`'s safe executor will intercept the call, generate a standardized error message, and recommend a specialist that can produce the missing artifact (e.g., `file_specialist`). This is more robust and maintainable than per-specialist implementation.

*   **Programmatic Task Completion:** To provide a deterministic signal that a task is finished, specialists that produce a final artifact (e.g., `web_builder`) set a `task_is_complete: True` flag in the state they return. The `RouterSpecialist` checks for this flag and, if present, routes to the `archiver_specialist` for a final report before ending the workflow.

*   **Iterative Refinement:** A specialist can improve its work over multiple steps. This is managed by including a cycle count (e.g., `refinement_cycles: 3`) in the `system_plan`. The `WebBuilder` specialist manages a counter in the `GraphState`. For each cycle, it generates HTML and then uses the `recommended_specialists` pattern to request a `CriticSpecialist` to review its work. This creates a controlled `WebBuilder -> Critic -> WebBuilder` loop. Once the cycles are complete, `WebBuilder` sets `task_is_complete: True`.

*   **Centralized State Integrity:**
    *   **Declarative State Updates:** The `GraphState` itself defines how its fields are updated (e.g., `messages: Annotated[List, operator.add]`), instructing LangGraph to always *append* to the message history, preventing accidental data loss.
    *   **Protective Wrappers:** The `ChiefOfStaff` wraps each specialist's execution in a "safe executor." This wrapper intercepts the specialist's output and sanitizes it before it's merged into the global state, providing centralized enforcement of global rules (like preventing specialists from modifying the `turn_count`).

## 4.0 How to Extend the System

### 4.1 Adding New Specialists

The primary way to extend the system's capabilities is by adding new specialists. For a detailed, step-by-step tutorial on this process, please refer to the **`How to Create a New Specialist`** guide.

### 4.2 Managing Dependencies

This project uses `pyproject.toml` as the single source of truth for dependencies and `pip-tools` to generate pinned `requirements.txt` files.

**To add or update a dependency:**
1.  Edit `pyproject.toml`.
2.  Run the sync script: `./scripts/sync-reqs.sh` (or `.bat` on Windows).
3.  Commit the changes to `pyproject.toml` **and** the generated `requirements.txt` files.

## 5.0 Project Structure Reference

For a comprehensive, file-by-file explanation of the project's structure, please see the **Project Structure Deep Dive** in `PROJECT_STRUCTURE.md`.
