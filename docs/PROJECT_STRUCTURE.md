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
-   `README.md`: The main entry point for understanding the project's purpose and features.
-   `Dockerfile`: Defines the Docker image for the application.
-   `langgraph-agentic-scaffold.code-workspace`: VS Code workspace file.
-   `runverify.sh`: Script to run end-to-end tests.
-   `ui.sh`: Script to run the Gradio UI.
-   `.gitignore`: Specifies files and directories to be ignored by Git.

## `app/`

This is the main Python package for the application.

-   `app/prompts/`: Contains all the `.md` prompt templates used by the LLM specialists. Separating prompts from code allows for easy editing and tuning without changing Python logic.
-   `app/src/`: The core source code of the application.
    -   `app/src/api.py`: The FastAPI application entry point. It defines the API endpoints (e.g., `/invoke`) and handles web requests.
    -   `app/src/ui/`: Contains the Gradio-based user interface.
        -   `gradio_app.py`: Defines the UI layout and event handling.
        -   `api_client.py`: A dedicated client for communicating with the backend API, separating UI logic from API logic.
    -   `app/src/cli.py`: The command-line interface for interacting with the agent.
    -   `app/src/specialists/`: The heart of the agentic system. Each `.py` file defines a `BaseSpecialist` subclass that encapsulates a specific skill (e.g., `file_specialist.py`, `web_builder.py`).
        -   `base.py`: Defines the `BaseSpecialist` abstract base class that all specialists must inherit from.
        -   `helpers.py`: Provides helper functions to reduce boilerplate in specialists, such as creating standardized "self-correction" responses.
        -   `archiver_specialist.py`: Specialist for archiving reports.
        -   `critic_specialist.py`: Specialist for critiquing artifacts.
        -   `data_extractor_specialist.py`: Specialist for extracting structured data.
        -   `data_processor_specialist.py`: Specialist for processing data.
        -   `default_responder_specialist.py`: Specialist for default responses.
        -   `end_specialist.py`: Specialist for ending the workflow.
        -   `file_specialist.py`: Specialist for file system operations.
        -   `hello_world.py`: Example specialist.
        -   `open_interpreter_specialist.py`: Specialist for executing code via open-interpreter.
        -   `prompt_specialist.py`: Specialist for general Q&A and instruction following.
        -   `prompt_triage_specialist.py`: Specialist for pre-flight prompt checks.
        -   `response_synthesizer_specialist.py`: Specialist for synthesizing final responses.
        -   `router_specialist.py`: The master router and planner.
        -   `sentiment_classifier_specialist.py`: Specialist for sentiment analysis.
        -   `structured_data_extractor.py`: Specialist for structured data extraction.
        -   `systems_architect.py`: Specialist for creating high-level technical plans.
        -   `text_analysis_specialist.py`: Specialist for text analysis.
        -   `web_builder.py`: Specialist for generating HTML documents.
        -   `schemas/`: A Python package containing all Pydantic models that define the data contracts for specialist inputs and outputs.
            -   `__init__.py`: Exposes all schemas for clean, unified imports.
            -   `_archiver.py`: Schema for archiver specialist.
            -   `_base.py`: Defines the `SpecialistOutput` envelope and other base schema components.
            -   `_critique.py`: Schema for critique specialist.
            -   `_data.py`: Schema for data specialists.
            -   `_file_ops.py`: Schema for file operations.
            -   `_orchestration.py`: Schema for orchestration.
            -   `_user_info.py`: Schema for user information.
            -   `_web.py`: Schema for web operations.
    -   `app/src/workflow/`: Contains the high-level orchestration logic.
        -   `app/src/workflow/graph_builder.py`: Responsible for reading the configuration, instantiating all specialists, enforcing architectural rules, and compiling the final `LangGraph` object.
        -   `app/src/workflow/graph_orchestrator.py`: Contains all the logic that is executed by the graph at runtime, such as the decider functions for conditional edges.
    -   `app/src/llm/`: Manages all interactions with Large Language Models.
        -   `app/src/llm/adapter.py`: Defines the `BaseAdapter` interface, ensuring all LLM providers have a consistent API within the system.
        -   `app/src/llm/adapters.py`: Contains various LLM adapters.
        -   `app/src/llm/adapters_helpers.py`: Helper functions for LLM adapters.
        -   `app/src/llm/factory.py`: The `AdapterFactory` reads the merged configuration and instantiates the correct adapter for a specialist.
        -   `app/src/llm/gemini_adapter.py`: Gemini LLM adapter.
        -   `app/src/llm/lmstudio_adapter.py`: LM Studio LLM adapter.
    -   `app/src/graph/`: Defines the shared state of the LangGraph.
        -   `app/src/graph/state.py`: Defines the `GraphState` `TypedDict`, which is the central data structure passed between all nodes in the graph. It uses `typing.Annotated` to define how state fields are merged (e.g., append to lists, update dictionaries).
        -   `app/src/graph/nodes.py`: Reserved for graph node definitions.
    -   `app/src/mcp/`: MCP (Message-Centric Protocol) for synchronous service invocation between specialists.
        -   `app/src/mcp/schemas.py`: Defines `McpRequest` and `McpResponse` Pydantic models for request/response contracts with auto-generated UUIDs for distributed tracing.
        -   `app/src/mcp/registry.py`: `McpRegistry` - per-graph-instance service registry with timeout protection and optional LangSmith tracing.
        -   `app/src/mcp/client.py`: `McpClient` - convenience wrapper providing `call()` (exception-based) and `call_safe()` (tuple-based) invocation patterns.
        -   `app/src/mcp/__init__.py`: Exports public MCP API (McpRegistry, McpClient, McpRequest, McpResponse).
    -   `app/src/utils/`: Contains shared utilities.
        -   `app/src/utils/config_loader.py`: The `ConfigLoader` class, responsible for loading, validating, and merging `config.yaml` and `user_settings.yaml`.
        -   `app/src/utils/config_schema.py`: The Pydantic models that define the schema for the configuration files, providing a single source of truth for validation.
        -   `app/src/utils/errors.py`: Custom error classes.
        -   `app/src/utils/path_utils.py`: Utility functions for path manipulation.
        -   `app/src/utils/prompt_loader.py`: A utility for loading prompt text from the `app/prompts/` directory.
        -   `app/src/utils/report_schema.py`: Schema for reports.
        -   `app/src/utils/state_pruner.py`: Utility for pruning state.
    -   `app/src/strategies/`: Contains different strategies for specialists.
        -   `app/src/strategies/critique/`: Critique strategies.
            -   `base.py`: Base class for critique strategies.
            -   `llm_strategy.py`: LLM-based critique strategy.
-   `app/tests/`: Contains all tests for the application, following a parallel structure to `app/src`.
    -   `app/tests/unit/`: Contains unit tests that test individual components in isolation. These tests use mocking extensively to avoid external dependencies like live LLM calls or running servers.
        -   `test_adapter_contracts.py`
        -   `test_api.py`
        -   `test_archiver_specialist.py`
        -   `test_base_schemas.py`
        -   `test_cli.py`
        -   `test_config_loader.py`
        -   `test_data_extractor_specialist.py`
        -   `test_file_ops_schemas.py`
        -   `test_file_specialist.py`
        -   `test_gradio_app.py`
        -   `test_graph_builder.py`
        -   `test_graph_orchestrator.py`
        -   `test_imports.py`
        -   `test_llm_factory.py`
        -   `test_lmstudio_adapter.py`
        -   `test_mcp_client.py`
        -   `test_mcp_registry.py`
        -   `test_mcp_schemas.py`
        -   `test_prompt_specialist.py`
        -   `test_response_synthesizer_specialist.py`
        -   `test_router_specialist.py`
        -   `test_sentiment_classifier_specialist.py`
        -   `test_specialist_loader.py`
        -   `test_structured_data_extractor.py`
        -   `test_text_analysis_specialist.py`
        -   `test_web_builder.py`
        -   `test_workflow_runner.py`
    -   `app/tests/integration/`: Intended for tests that verify the interaction between multiple components.
        -   `test_live_llm.py`
        -   `test_live_lmstudio.py`

## `logs/`
-   Contains log files generated by the FastAPI server. Ignored by Git.

## `docs/`

Contains all project documentation.

-   `docs/DEVELOPERS_GUIDE.md`: The primary guide for developers on system architecture, patterns, and how to extend the system.
-   `docs/CREATING_A_NEW_SPECIALIST.md`: A step-by-step tutorial for adding new specialists.
-   `docs/PROJECT_STRUCTURE.md`: (This file) A detailed breakdown of the repository layout.
-   `docs/UX_UI & API Mockup Guide.md`: UX/UI and API Mockup Guide.
-   `docs/ADR/`: Contains Architecture Decision Records (ADRs) that document key architectural choices and their rationale for historical context.

## `scripts/`

A collection of helper scripts to simplify common development tasks. These scripts ensure consistency across different developer environments (Linux, macOS, Windows).

-   `install.sh`/`.bat`: Sets up the development environment.
-   `server.sh`/`.bat`: Manages the FastAPI server (start, stop, restart).
-   `server.py`: Python script for starting the server.
-   `cli.sh`/`.bat`: A convenience wrapper for running `app/src/cli.py`.
-   `sync-reqs.sh`/`.bat`: Regenerates `requirements.txt` files from `pyproject.toml` using `pip-tools`.
-   `verify.sh`: Runs a quick end-to-end test of the system.
