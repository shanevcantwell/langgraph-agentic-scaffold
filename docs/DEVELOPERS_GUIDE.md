# Developer's Guide

This guide serves as the central hub for all developer documentation. The documentation has been split into focused guides to make it easier to find the information you need.

## Core Documentation

*   **[System Architecture](./ARCHITECTURE.md)**
    *   Mission & Philosophy
    *   Core Components (Specialists, Router, Orchestrator)
    *   State Management (Breaking Changes & Migration)
    *   Architectural Patterns (Virtual Coordinator, Resilience Layer)
    *   Best Practices

*   **[Configuration Guide](./CONFIGURATION_GUIDE.md)**
    *   The 3-Tiered Configuration System (`.env`, `config.yaml`, `user_settings.yaml`)
    *   Environment Variable Interpolation
    *   Container Naming Conventions

*   **[MCP (Message-Centric Protocol) Guide](./MCP_GUIDE.md)**
    *   Synchronous Service Calls
    *   Service Registration & Invocation
    *   Available Services (FileSpecialist)
    *   Troubleshooting

*   **[Observability Guide](./OBSERVABILITY.md)**
    *   LangSmith Integration
    *   Tracing & Debugging

*   **[Creating a New Specialist](./CREATING_A_NEW_SPECIALIST.md)**
    *   Step-by-step tutorial for adding custom specialists
    *   Standard vs. Procedural Specialists
    *   Testing Guide

*   **[Integration Test Guide](./INTEGRATION_TEST_GUIDE.md)**
    *   Patterns and examples for writing integration tests

*   **[Graph Construction Guide](./GRAPH_CONSTRUCTION_GUIDE.md)**
    *   Subgraph patterns and workflow composition

*   **[UX/UI & API Guide](./UX_UI_GUIDE.md)**
    *   API contracts and data structures for UI development
    *   Streaming response format and SSE events

*   **[Project Structure](./PROJECT_STRUCTURE.md)**
    *   Detailed breakdown of the repository layout

## Quick Reference

### Common Tasks

*   **Add a new LLM provider:** Edit `user_settings.yaml`
*   **Change the default model:** Edit `user_settings.yaml` -> `default_llm_config`
*   **Add a new specialist:** See [Creating a New Specialist](./CREATING_A_NEW_SPECIALIST.md)
*   **Debug a failed run:** Check LangSmith traces (see [Observability Guide](./OBSERVABILITY.md))

### Key Directories

*   `app/src/specialists/`: Specialist implementations
*   `app/prompts/`: LLM prompts
*   `config.yaml`: System blueprint
*   `user_settings.yaml`: Local overrides & model bindings
