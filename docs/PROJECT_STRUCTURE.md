# Project Structure Deep Dive

This document provides a detailed breakdown of the directory and file structure for the `langgraph-agentic-scaffold`. It is intended to give developers a clear map of the codebase.

## Root Directory

The root of the project contains configuration, dependency management, and high-level scripts.

-   `.env`: (Local only) Stores secrets like API keys. Ignored by Git.
-   `.env.example`: An example template for the `.env` file.
-   `config.yaml`: The developer's architectural blueprint for the agentic system. Defines all possible providers and specialists. This file **should** be committed to source control.
-   `config.yaml.example`: An example template for `config.yaml`.
-   `user_settings.yaml`: (Local only) The user's choices, binding specialists to specific LLM configurations from `config.yaml`. Ignored by Git.
-   `user_settings.yaml.example`: An example template for `user_settings.yaml`.
-   `pyproject.toml`: The single source of truth for project metadata and dependencies, managed by `pip-tools`.
-   `requirements.txt`: Pinned production dependencies, generated from `pyproject.toml`.
-   `requirements-dev.txt`: Pinned development dependencies, generated from `pyproject.toml`.
-   `README.md`: The main entry point for understanding the project's purpose and features.
-   `LICENSE`: The MIT license file.
-   `.gitignore`: Specifies files and directories to be ignored by Git.

## `app/`

This is the main Python package for the application.

-   `app/prompts/`: Contains all the `.md` prompt templates used by the LLM specialists. Separating prompts from code allows for easy editing and tuning without changing Python logic.
-   `app/src/`: The core source code of the application.
    -   `app/src/api.py`: The FastAPI application entry point. It defines the API endpoints (e.g., `/invoke`) and handles web requests.
    -   `app/src/cli.py`: The command-line interface for interacting with the running API server.
    -   `app/src/specialists/`: The heart of the agentic system. Each `.py` file defines a `BaseSpecialist` subclass that encapsulates a specific skill (e.g., `file_specialist.py`, `web_builder.py`).
        -   `app/src/specialists/base.py`: Defines the `BaseSpecialist` abstract base class that all specialists must inherit from.
    -   `app/src/workflow/`: Contains the high-level orchestration logic.
        -   `app/src/workflow/chief_of_staff.py`: Responsible for reading the configuration, instantiating all specialists, and compiling the final `LangGraph` object.
    -   `app/src/llm/`: Manages all interactions with Large Language Models.
        -   `app/src/llm/adapter.py`: Defines the `BaseAdapter` interface, ensuring all LLM providers have a consistent API within the system.
        -   `app/src/llm/adapters.py`: Contains the concrete implementations for each LLM provider (e.g., `GeminiAdapter`, `LMStudioAdapter`).
        -   `app/src/llm/factory.py`: The `AdapterFactory` reads the merged configuration and instantiates the correct adapter for a specialist.
    -   `app/src/graph/`: Defines the shared state of the LangGraph.
        -   `app/src/graph/state.py`: Defines the `GraphState` `TypedDict`, which is the central data structure passed between all nodes in the graph.
    -   `app/src/utils/`: Contains shared utilities.
        -   `app/src/utils/config_loader.py`: The `ConfigLoader` class, responsible for loading, validating, and merging `config.yaml` and `user_settings.yaml`.
        -   `app/src/utils/config_schema.py`: The Pydantic models that define the schema for the configuration files, providing a single source of truth for validation.
        -   `app/src/utils/prompt_loader.py`: A utility for loading prompt text from the `app/prompts/` directory.
-   `app/tests/`: Contains all unit and integration tests for the application, following a parallel structure to `app/src`.

## `docs/`

Contains all project documentation.

-   `docs/DEVELOPERS_GUIDE.md`: The primary guide for developers on system architecture, patterns, and how to extend the system.
-   `docs/CREATING_A_NEW_SPECIALIST.md`: A step-by-step tutorial for adding new specialists.
-   `docs/PROJECT_STRUCTURE.md`: (This file) A detailed breakdown of the repository layout.
-   `docs/adr/`: Contains Architecture Decision Records (ADRs) that document key architectural choices and their rationale.

## `external/`

A designated directory for placing third-party code that might be "wrapped" by a `WrappedSpecialist`. It is kept in Git via `.gitkeep` but its contents are ignored.

## `scripts/`

A collection of helper scripts to simplify common development tasks. These scripts ensure consistency across different developer environments (Linux, macOS, Windows).

-   `install.sh`/`.bat`: Sets up the development environment.
-   `server.sh`/`.bat`: Manages the FastAPI server (start, stop, restart).
-   `cli.sh`/`.bat`: A convenience wrapper for running `app/src/cli.py`.
-   `verify.sh`/`.ps1`: Runs a quick end-to-end test of the system.
-   `sync-reqs.sh`/`.bat`: Regenerates `requirements.txt` files from `pyproject.toml` using `pip-tools`.