---
applyTo: '**'
---
ALWAYS run tests and scripts using `docker compose run --rm app <command>`.
NEVER run `pytest` or `python` directly in the shell. Integration tests WILL FAIL outside Docker.
ALWAYS run `pytest` *narrowest subset first*. There is an enormous suite of unit AND integration tests that take 10-15 minutes to run on a good day.
ALWAYS update documentation in `./docs`, as well as any documents such as roadmaps or plans that are affected.
ALWAYS ensure unit and integration tests are up to date with ALL changes and additions to the code base. Commit your work but only after ensuring the full test suite successfully completes.
ALWAYS commit changes in sensible, logical chunks following successful testing. Do not squash unrelated features into a single massive commit.

## **Escape Hatch (Clarification Triage)**
*   **Be Aware of What is Outside Your Scope**: Asking the user for clarification is an acceptable solution in cases where you find yourself lost or churning apparently from outside factors, e.g. when 1. a test case just does not appear to be fixable or attempts with it have crossed more than one context summarize/compact process; or 2. integration tests are failing across the board, pointing to an issue at the server layer that the user may need to address.

## Project Vision & Metaphor (The Cathedral & The Codex)
This project is **Phase I** of a multi-phase journey toward a **Governed, State-Aware Agentic System**.
*   **The Cathedral**: The resilient institutional architecture that survives model replacement.
*   **The Codex**: Multi-layered persistent memory (episodic, semantic, procedural).
*   **The Craftsmen**: The LLMs, which are treated as interchangeable components.
*   **The Lectern**: The finite working memory (context window).

**Critical Insight**: We are building infrastructure that will support much more sophisticated cognition later. Every architectural decision must balance immediate functionality with long-term adaptability.

## Architectural Pillars
1.  **Aggressive Resilience**: Zero-tolerance for silent failures. Fail-fast validation, circuit breakers, system-wide invariant monitoring.
2.  **Explicit State as Control Plane**: Move from LLM inference for control flow to structured data (MCP, Routing Plans).
3.  **Hybrid Routing Engine**: Multi-stage decision architecture (Procedural -> Declarative -> Probabilistic).
4.  **Professionalized Platform**: Mature infrastructure, observability (LangSmith, AG-UI), and service-oriented deployment.

## Core Mandates
*   **Low-Wattage Constraint**: Must work with open-weight models running locally (20b-36b parameters). Keep prompts simple.
*   **Fail-Fast**: Silent failures are unacceptable. Errors must be loud and actionable.
*   **State Hygiene**:
    *   `Scratchpad`: Ephemeral communication (cleared after routing).
    *   `Artifacts`: Structured outputs.
    *   `Messages`: Permanent conversation history.
    *   **Parallel nodes NEVER write to messages**.
*   **Model-Agnostic**: No hardcoded model dependencies. Bindings in `user_settings.yaml`.
*   **Separation of Concerns**:
    *   **Router**: Decides **WHAT** (capability needed).
    *   **Orchestrator**: Decides **HOW** (implementation/fan-out).
*   **IT Boundary (The "Call I.T." Rule)**: Do not modify server infrastructure (`.env`, `user_settings.yaml`, Docker configs). Accept these settings as immutable facts. If a failure occurs due to environment/server configuration, STOP and report it to the user. You are not credentialed to handle the server layer.
*   **Proactive Stewardship**: If you encounter configuration oddities (e.g., `.gitignore` ignoring itself, recursive paths, or illogical settings), **flag them to the user immediately**. Do not silently work around them unless necessary for the immediate task, and even then, leave a note.
*   **Escape Hatch (Clarification)**

## Key Design Patterns
*   **Virtual Coordinator**: Router chooses capability -> Orchestrator intercepts and decides implementation (e.g., fan-out).
*   **Subgraphs**: Use direct edges for tight loops (e.g., Web Builder <-> Critic) to avoid Router overhead.
*   **MCP (Message-Centric Protocol)**: Use for synchronous, direct service invocation between specialists.
*   **Atomic Archival**: Use `.zip` packages for high-fidelity observability.

## Current Status (Nov 2025)
*   **Completed**: Workstream 1 (Resilience), Workstream 2 (MCP/Control Plane), Workstream 3 (Hybrid Routing/Scatter-Gather).
*   **Active**: Workstream 4 (Platform & Tooling) - specifically UI/UX and Archival.
*   **Deferred**: Dossier Pattern, Diplomatic Process (CHAT-003).