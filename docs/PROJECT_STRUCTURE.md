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
-   `docker-compose.yml`: Multi-container orchestration (app + proxy services).
-   `langgraph-agentic-scaffold.code-workspace`: VS Code workspace file.
-   `runverify.sh`: Script to run end-to-end tests.
-   `ui.sh`: Script to run the Gradio UI.
-   `.gitignore`: Specifies files and directories to be ignored by Git.

## `app/`

This is the main Python package for the application.

-   `app/prompts/`: Contains all the `.md` prompt templates used by the LLM specialists. Separating prompts from code allows for easy editing and tuning without changing Python logic.
-   `app/src/`: The core source code of the application.
    -   `app/src/api.py`: The FastAPI application entry point. It defines the API endpoints (e.g., `/invoke`) and handles web requests.
    -   `app/src/ui/`: Contains the Gradio-based user interfaces.
        -   `gradio_app.py`: Original Gradio UI.
        -   `gradio_vegas.py`: LAS VEGAS Terminal UI (production interface).
        -   `api_client.py`: A dedicated client for communicating with the backend API, separating UI logic from API logic.
    -   `app/src/cli.py`: The command-line interface for interacting with the agent.

    ### `app/src/specialists/`

    The heart of the agentic system. Each `.py` file defines a `BaseSpecialist` subclass that encapsulates a specific skill.

    **Note:** The flat directory structure is maintained per ADR-CORE-013, pending MCP container migration. Specialists are categorized below for discoverability.

    **Core Infrastructure** (2 specialists):
    -   `base.py`: Defines the `BaseSpecialist` abstract base class that all specialists must inherit from. Includes `_get_enriched_messages()` helper for context injection.
    -   `helpers.py`: Provides helper functions to reduce boilerplate in specialists, such as creating standardized "self-correction" responses.

    **Workflow & Orchestration** (6 specialists):
    -   `router_specialist.py`: The master router and planner. Decides which specialist to route to next.
    -   `triage_architect.py`: Pre-flight context engineering. Creates plans for gathering context before routing (ContextPlan with LIST_DIRECTORY, READ_FILE, RESEARCH actions).
    -   `facilitator_specialist.py`: Executes context-gathering plans from Triage (LIST_DIRECTORY, READ_FILE, RESEARCH actions).
    -   `prompt_triage_specialist.py`: Pre-flight prompt checks (deprecated/replaced by triage_architect).
    -   `critic_specialist.py`: Critiques artifacts and provides revision feedback (generate-critique-refine subgraph pattern).
    -   `end_specialist.py`: Centralized termination point. Synthesizes final response and triggers archival.

    **File Operations** (4 specialists):
    -   `file_specialist.py`: MCP service layer for file system operations (list, read, write, delete, rename). Procedural implementation.
    -   `file_operations_specialist.py`: User-facing interface layer that interprets file operation requests via LLM tool calling, routes to `file_specialist` via MCP.
    -   `batch_processor_specialist.py`: Handles batch file operations with internal iteration pattern (e.g., "move all txt files to appropriate folders").
    -   `image_specialist.py`: Image analysis and processing specialist.

    **Analysis & Data Processing** (5 specialists):
    -   `text_analysis_specialist.py`: Text analysis and natural language processing.
    -   `data_extractor_specialist.py`: Extracting structured data from unstructured sources.
    -   `data_processor_specialist.py`: Data transformation and processing.
    -   `structured_data_extractor.py`: Structured data extraction with schema validation.
    -   `sentiment_classifier_specialist.py`: Sentiment analysis and classification.

    **Communication & Response** (7 specialists):
    -   `chat_specialist.py`: Conversational specialist for general Q&A (part of tiered chat subgraph).
    -   `progenitor_alpha_specialist.py`: Analytical perspective provider for tiered chat (CORE-CHAT-002).
    -   `progenitor_bravo_specialist.py`: Contextual perspective provider for tiered chat (CORE-CHAT-002).
    -   `tiered_synthesizer_specialist.py`: Combines Alpha and Bravo perspectives into formatted output (CORE-CHAT-002).
    -   `prompt_specialist.py`: General-purpose Q&A and instruction following.
    -   `default_responder_specialist.py`: Handles simple greetings and default responses.
    -   `hello_world_specialist.py`: Example specialist for onboarding and testing.

    **Generation & Planning** (3 specialists):
    -   `web_builder.py`: Generates HTML documents from specifications.
    -   `systems_architect.py`: Creates high-level technical plans and architectural designs.
    -   `summarizer_specialist.py`: MCP service for text summarization and condensation.

    **Research & External Data** (3 specialists):
    -   `project_director.py`: Manages complex research projects using an emergent state machine (ProjectContext).
    -   `web_specialist.py`: Procedural worker for executing atomic web tasks (search/browse).
    -   `open_interpreter_specialist.py`: Executes code via open-interpreter framework (may migrate to MCP container).

    **Distillation Subgraph** (4 specialists):
    -   `distillation_coordinator_specialist.py`: Coordinates the distillation workflow.
    -   `distillation_prompt_expander_specialist.py`: Expands user prompts into multiple variations.
    -   `distillation_prompt_aggregator_specialist.py`: Aggregates expanded prompts for processing.
    -   `distillation_response_collector_specialist.py`: Collects and synthesizes distillation responses.

    **System Utilities** (1 specialist):
    -   `archiver_specialist.py`: Archives workflow completion reports to `./logs/archive/*.md` with state snapshots.

    ### `app/src/specialists/schemas/`

    A Python package containing all Pydantic models that define the data contracts for specialist inputs and outputs.

    -   `__init__.py`: Exposes all schemas for clean, unified imports.
    -   `_archiver.py`: Schema for archiver specialist.
    -   `_base.py`: Defines the `SpecialistOutput` envelope and other base schema components.
    -   `_critique.py`: Schema for critique specialist.
    -   `_data.py`: Schema for data specialists.
    -   `_file_ops.py`: Schema for file operations.
    -   `_orchestration.py`: Schema for orchestration.
    -   `_user_info.py`: Schema for user information.
    -   `_web.py`: Schema for web operations.

    ### `app/src/workflow/`

    Contains the high-level orchestration logic.

    -   `graph_builder.py`: Responsible for reading the configuration, instantiating all specialists, enforcing architectural rules, and compiling the final `LangGraph` object.
    -   `graph_orchestrator.py`: Contains all the logic that is executed by the graph at runtime, such as the decider functions for conditional edges.
    -   `runner.py`: Workflow execution runtime and entry point.

    ### `app/src/llm/`

    Manages all interactions with Large Language Models.

    -   `adapter.py`: Defines the `BaseAdapter` interface, ensuring all LLM providers have a consistent API within the system.
    -   `factory.py`: The `AdapterFactory` reads the merged configuration and instantiates the correct adapter for a specialist.
    -   `gemini_adapter.py`: Google Gemini LLM adapter.
    -   `lmstudio_adapter.py`: LM Studio LLM adapter for local model execution.
    -   `anthropic_adapter.py`: Anthropic Claude adapter (if configured).
    -   `openai_adapter.py`: OpenAI GPT adapter (if configured).

    ### `app/src/graph/`

    Defines the shared state of the LangGraph.

    -   `state.py`: Defines the `GraphState` `TypedDict`, which is the central data structure passed between all nodes in the graph. It uses `typing.Annotated` to define how state fields are merged (e.g., append to lists, update dictionaries).
    -   `state_factory.py`: Factory for creating properly structured `GraphState` objects for runtime and testing.
    -   `nodes.py`: Reserved for graph node definitions.

    ### `app/src/resilience/`

    Contains the system's resilience and stability components.

    -   `invariants.py`: Defines the formal rules (State Integrity and Execution Constraints) that constitute a healthy system state.
    -   `monitor.py`: The `InvariantMonitor` service that acts as a circuit breaker, checking invariants before every specialist execution.

    ### `app/src/mcp/`

    MCP (Message-Centric Protocol) for synchronous and asynchronous service invocation between specialists.

    -   `schemas.py`: Defines `McpRequest` and `McpResponse` Pydantic models for request/response contracts with auto-generated UUIDs for distributed tracing.
    -   `registry.py`: `McpRegistry` - per-graph-instance service registry with timeout protection and optional LangSmith tracing.
    -   `client.py`: `McpClient` - convenience wrapper providing `call()` (exception-based) and `call_safe()` (tuple-based) invocation patterns.
    -   `external_client.py`: `ExternalMcpClient` - async client for external MCP servers (Node.js, Docker containers) with JSON-RPC over stdio (ADR-MCP-003).
    -   `__init__.py`: Exports public MCP API (McpRegistry, McpClient, McpRequest, McpResponse, ExternalMcpClient).

    ### `app/src/interface/`

    Interface adapters and translators for different client types.

    -   `context_schema.py`: Pydantic schemas for context engineering (ContextPlan, ContextAction, ContextActionType).
    -   `translator.py`: AG UI event translator (translates LangGraph events to AG UI format).

    ### `app/src/utils/`

    Contains shared utilities.

    -   `config_loader.py`: The `ConfigLoader` class, responsible for loading, validating, and merging `config.yaml` and `user_settings.yaml`.
    -   `config_schema.py`: The Pydantic models that define the schema for the configuration files, providing a single source of truth for validation.
    -   `errors.py`: Custom error classes (ProxyError, SafetyFilterError, RateLimitError, CircuitBreakerTriggered, etc.).
    -   `path_utils.py`: Utility functions for path manipulation and validation.
    -   `prompt_loader.py`: A utility for loading prompt text from the `app/prompts/` directory.
    -   `report_schema.py`: Schema definitions for report generation.
    -   `state_pruner.py`: Utility for pruning and cleaning state objects.
    -   `verify_connectivity.py`: Network connectivity verification for proxy and external services.
    -   `cancellation_manager.py`: Manages cancellation tokens for long-running operations.

    ### `app/src/strategies/`

    Contains different strategies for specialists.

    -   `critique/`: Critique strategies.
        -   `base.py`: Base class for critique strategies.
        -   `llm_strategy.py`: LLM-based critique strategy.

## `app/tests/`

Contains all tests for the application, following a parallel structure to `app/src`.

-   `conftest.py`: Centralized pytest fixtures for consistent test infrastructure.
-   `app/tests/unit/`: Contains unit tests that test individual components in isolation. These tests use mocking extensively to avoid external dependencies like live LLM calls or running servers.
    -   `test_adapter_contracts.py`: Verifies LLM adapter contract compliance.
    -   `test_ag_ui_translator.py`: Tests AG UI event translation.
    -   `test_api.py`: API endpoint tests.
    -   `test_archiver_specialist.py`: Archiver specialist tests.
    -   `test_base_schemas.py`: Base schema validation tests.
    -   `test_batch_processor_specialist.py`: Batch processor tests.
    -   `test_circuit_breaker.py`: Invariant monitor and circuit breaker tests.
    -   `test_cli.py`: CLI tests.
    -   `test_config_loader.py`: Configuration loading and merging tests.
    -   `test_context_engineering_graph.py`: Context engineering subgraph wiring tests.
    -   `test_data_extractor_specialist.py`: Data extractor tests.
    -   `test_facilitator.py`: Facilitator specialist tests (context gathering).
    -   `test_file_ops_schemas.py`: File operations schema tests.
    -   `test_file_operations_specialist.py`: File operations specialist tests.
    -   `test_file_specialist.py`: File specialist MCP service tests.
    -   `test_gradio_app.py`: Gradio UI tests.
    -   `test_graph_builder.py`: Graph construction and wiring tests.
    -   `test_graph_orchestrator.py`: Runtime orchestration logic tests.
    -   `test_imports.py`: Import validation tests.
    -   `test_llm_factory.py`: LLM adapter factory tests.
    -   `test_lmstudio_adapter.py`: LM Studio adapter tests.
    -   `test_mcp_client.py`: MCP client tests.
    -   `test_mcp_registry.py`: MCP registry tests.
    -   `test_mcp_schemas.py`: MCP schema tests.
    -   `test_open_interpreter_specialist.py`: Open interpreter specialist tests.
    -   `test_progenitor_alpha.py`: ProgenitorAlpha specialist tests.
    -   `test_progenitor_bravo.py`: ProgenitorBravo specialist tests.
    -   `test_prompt_specialist.py`: Prompt specialist tests.
    -   `test_response_synthesizer_specialist.py`: Response synthesis tests.
    -   `test_router_specialist.py`: Router specialist tests.
    -   `test_sentiment_classifier_specialist.py`: Sentiment classifier tests.
    -   `test_specialist_loader.py`: Specialist instantiation tests.
    -   `test_structured_data_extractor.py`: Structured data extraction tests.
    -   `test_text_analysis_specialist.py`: Text analysis tests.
    -   `test_tiered_synthesizer.py`: Tiered chat synthesizer tests.
    -   `test_web_builder.py`: Web builder specialist tests.
    -   `test_workflow_runner.py`: Workflow runner tests.
-   `app/tests/integration/`: Intended for tests that verify the interaction between multiple components.
    -   `test_external_mcp.py`: External MCP container integration tests (ADR-MCP-003).
    -   `test_live_llm.py`: Live LLM integration tests (Google Gemini).
    -   `test_live_lmstudio.py`: Live LM Studio integration tests.
    -   `test_startup_validation.py`: Fail-fast startup validation tests.

## `logs/`
-   Contains log files generated by the FastAPI server. Ignored by Git.
-   `agentic_server.log`: Main application debug log.
-   `archive/`: Workflow completion reports generated by ArchiverSpecialist.

## `docs/`

Contains all project documentation.

-   `DEVELOPERS_GUIDE.md`: The central hub for all developer documentation.
-   `ARCHITECTURE.md`: Core system architecture and design patterns.
-   `PROJECT_STRUCTURE.md`: (This file) A detailed breakdown of the repository layout.
-   `CONFIGURATION_GUIDE.md`: Guide to the 3-tiered configuration system.
-   `MCP_GUIDE.md`: Guide to the Message-Centric Protocol (MCP).
-   `OBSERVABILITY.md`: Guide to LangSmith integration and debugging.
-   `CREATING_A_NEW_SPECIALIST.md`: A step-by-step tutorial for adding new specialists.
-   `INTEGRATION_TEST_GUIDE.md`: Guide to writing integration tests.
-   `GRAPH_CONSTRUCTION_GUIDE.md`: Guide to graph construction and subgraphs.
-   `UX_UI_GUIDE.md`: UX/UI and API integration guide.
-   `TEST_SUITE_SUMMARY.md`: Test suite organization and coverage summary.
-   `SAMPLE_ARCHIVER_OUTPUT.md`: Example archive report output.

### `docs/ADR/`

Architecture Decision Records (ADRs) documenting key architectural decisions.

-   `ADR-CORE-013-Specialist-Organization-Strategy.md`: Flat directory structure rationale.
-   `ADR-MCP-003-External-MCP-Container-Integration.md`: External MCP design and implementation.
-   `ADR-CORE-014-Async-Graph-Execution-Migration.md`: Async execution migration path.

**Note:** Most ADRs and blueprints have been moved to the `design-docs` repository (sibling to this repo, added to VS Code workspace). See `../design-docs/agentic-scaffold/03_ADRS/` for active ADRs and `/01_BLUEPRINTS/` for vision documents.

## `scripts/`

A collection of helper scripts to simplify common development tasks. These scripts ensure consistency across different developer environments (Linux, macOS, Windows).

-   `install.sh`/`.bat`: Sets up the development environment.
-   `server.sh`/`.bat`: Manages the FastAPI server (start, stop, restart).
-   `server.py`: Python script for starting the server.
-   `cli.sh`/`.bat`: A convenience wrapper for running `app/src/cli.py`.
-   `sync-reqs.sh`/`.bat`: Regenerates `requirements.txt` files from `pyproject.toml` using `pip-tools`.
-   `verify.sh`: Runs a quick end-to-end test of the system.

## `proxy/`

Squid proxy configuration for whitelisting external access.

-   `squid.conf`: Proxy configuration with domain whitelisting for security.
-   `Dockerfile`: Proxy container image definition.

## `workspace/`

User workspace for file operations and external document storage. Mounted into containers for file specialist access.

-   `design-docs/`: External design documents and ADRs (git submodule or sibling repo).

## Specialist Count

**Total Specialists:** 35 specialist modules
- **LLM-driven:** ~20 specialists (router, chat, progenitors, data analysis, generation, etc.)
- **Procedural:** ~15 specialists (file_specialist, facilitator, archiver, synthesizers, etc.)
- **MCP Services:** 3 (file_specialist, web_specialist, summarizer_specialist)

## Key Architectural Files

The following files are critical to understanding the system architecture:

1.  **`app/src/specialists/base.py`:** All specialists inherit from `BaseSpecialist`.
2.  **`app/src/graph/state.py`:** The central `GraphState` data structure.
3.  **`app/src/workflow/graph_builder.py`:** Graph construction and wiring logic.
4.  **`app/src/workflow/graph_orchestrator.py`:** Runtime decision logic.
5.  **`app/src/workflow/executors/node_executor.py`:** Safe execution wrapper and invariant enforcement.
6.  **`app/src/mcp/registry.py`:** MCP service registration and discovery.
7.  **`app/src/resilience/monitor.py`:** System invariant monitoring and circuit breaker.
8.  **`config.yaml`:** Architectural blueprint defining all system components.
9.  **`user_settings.yaml`:** Runtime model bindings and feature toggles.
