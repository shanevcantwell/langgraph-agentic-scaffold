# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems

<img width="3407" height="2072" alt="LangGraph Agentic Scaffold Architecture Diagram" src="https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1" />

[](https://opensource.org/licenses/MIT)
[](https://www.python.org/downloads/)
[](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.
---
<img width="1955" height="1096" alt="{FD3D8427-8962-4787-8AD0-13F00AF671AC}" src="https://github.com/user-attachments/assets/315e79c0-e7eb-40d3-b4b6-0252c649194c" />

### 🎥 Video Briefings

| 5-Minute Developer Briefing | 90-Second Elevator Pitch |
| :---: | :---: |
| [![Watch the 5-Minute Briefing](https://github.com/user-attachments/assets/0bf289cf-da47-48d5-b0b9-ce54fd72486d)](https://www.youtube.com/watch?v=KfqKRXvznDc) | [![Listen to the 90-Second Pitch](https://github.com/user-attachments/assets/155d60bc-be1c-4508-a46c-341bdebfd69c)](http://reflectiveattention.ai/videos/Unlocking_Multi-Agent_AI__Elevator_Pitch_for_the_Langgraph-Agen.mp4) |
| A complete technical rundown of the scaffold's architecture, mission, and how to get started. | A concise, audio-only overview of the project's value proposition. |

## Mission & Philosophy

The mission is to provide a clear, maintainable, and testable template for constructing multi-agent systems. The core philosophy is a separation of concerns, where the system is composed of distinct agent types:

  * **Specialists (`BaseSpecialist`):** Modular agents that perform a single, well-defined task. The system supports both LLM-driven specialists for complex reasoning and deterministic "procedural" specialists for reliable, code-based actions.
  * **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph.
  * **Structural Orchestrator (`GraphBuilder`):** A high-level system component responsible for reading the configuration, instantiating all specialists, and compiling the final `LangGraph` instance before execution.

## Architectural Highlights

This scaffold provides a well-defined architecture designed for reliability, scalability, and resilience.

### Core Architecture Patterns

  * **API-First Design:** The system is exposed via a FastAPI web server with sample Gradio UIs, providing clean, modern interfaces for interaction and integration.

  * **Configuration-Driven:** The entire agentic system—specialists, models, and prompts—is defined in configuration files. The system's structure does not depend on changing Python code.

  * **Three-Tiered Configuration System:**
    - **Tier 1 (`.env`)**: Secrets and environment-specific settings (API keys, connection URLs)
    - **Tier 2 (`config.yaml`)**: Architectural blueprint defining all possible components (committed to git)
    - **Tier 3 (`user_settings.yaml`)**: Model bindings and runtime configuration (git-ignored)
    - **Environment Variable Interpolation**: Supports `${VAR_NAME}` and `${VAR_NAME:-default}` syntax for single-source-of-truth configuration

  * **MCP (Message-Centric Protocol):** Synchronous, direct service invocation between specialists with timeout controls and LangSmith tracing. Enables specialists to call each other's functions without routing through the graph, reducing latency and LLM costs.

  * **Virtual Coordinator Pattern:** Transparent upgrade from single-node capabilities to multi-node subgraphs. The Router chooses WHAT capability is needed, while the Orchestrator decides HOW to implement it. Exemplified by the Tiered Chat Subgraph.

  * **Tiered Chat Subgraph (CORE-CHAT-002):** Production-ready multi-perspective chat with:
    - Parallel execution of analytical and contextual specialists (ProgenitorAlpha/Bravo)
    - Fan-out/fan-in graph pattern with proper state management
    - Graceful degradation when components fail
    - 39 comprehensive tests ensuring reliability

### Reliability & Observability

  * **Fail-Fast Validation:**
    - **Connectivity Check:** Startup script (`verify_connectivity.py`) validates internet access and LLM provider reachability *before* the application starts. Prevents "zombie" containers that look healthy but can't work.
    - **Route Validation:** Eliminates silent infinite-loop bugs by validating graph edges at build time.
    - **System Invariants:** Runtime monitor enforces structural integrity and prevents invalid state transitions.

  * **First-Class Observability:** Integrated with LangSmith out of the box. FastAPI `lifespan` manager ensures buffered traces are sent before exit. Essential for debugging complex multi-agent interactions.

  * **Schema-Enforced Reliability:** Pydantic models define "hard contracts" for LLM outputs, dramatically reducing runtime errors and validation boilerplate.

  * **Robust Termination Sequence:** Mandatory three-stage finalization (specialist signals completion → EndSpecialist synthesizes → Router archives) ensures predictable shutdown.

### Developer Experience

  * **Decoupled Adapter Pattern:** Specialists request pre-configured "adapters" by name, allowing you to swap LLM providers (Gemini, OpenAI, LM Studio, etc.) without touching business logic.

  * **Model-Agnostic Architecture:** All model bindings are runtime configuration. Develop with local models, deploy with cloud APIs—no code changes required.

  * **Comprehensive Documentation:**
    - Developer's Guide (architecture, patterns, best practices)
    - Specialist Creation Guide (step-by-step tutorial)
    - Integration Test Guide (testing patterns and examples)
    - Graph Construction Guide (subgraph patterns)

  * **Modern Python Tooling:** Uses `pyproject.toml` and `pip-tools` to ensure reproducible and reliable builds for both production and development.

## ⚠️ A Critical Note on Security

This scaffold grants significant power to one or more LLMs that you define as specialists. The tools you create can execute real code, access your file system, and make external API calls with your keys.

> [\!WARNING]
> **You are granting the configured LLM direct control over these powerful tools.**
>
> An agentic system can create feedback loops that **amplify** a simple misunderstanding over many iterations. This emergent behavior can lead to complex, unintended, and irreversible actions like file deletion or data exposure.
>
> **Always run this project in a secure, sandboxed environment (like a Docker container or a dedicated VM).**

## Getting Started with Docker (Recommended)

Using Docker is the recommended way to run this project. It provides a secure, sandboxed environment and guarantees a consistent setup.

### Prerequisites

  * Docker and Docker Compose

### Installation & Setup

1.  **Clone the Repository**

    ```bash
    git clone https://github.com/shanevcantwell/langgraph-agentic-scaffold.git
    cd langgraph-agentic-scaffold
    ```

2.  **Configure Your Environment**

      * Copy the example environment file: `cp .env.example .env`
      * Edit the new `.env` file to add your API keys (e.g., `GOOGLE_API_KEY`, `LANGSMITH_API_KEY`).
      * **Crucially**, to connect to local model servers (like LM Studio or Ollama) running on your host machine:
        1. Use the special `host.docker.internal` hostname in your URLs.
        2. Ensure `host.docker.internal` is added to your `NO_PROXY` environment variable if you are behind a corporate proxy or using the included Squid proxy.
      * Copy the proxy configuration: `cp proxy/squid.conf.example proxy/squid.conf`
        ```dotenv
        # .env
        # Use host.docker.internal to connect from the container to services on the host.
        LMSTUDIO_BASE_URL="http://host.docker.internal:1234/v1/"
        OLLAMA_BASE_URL="http://host.docker.internal:11434"
        
        # Ensure local traffic bypasses the proxy
        NO_PROXY=localhost,127.0.0.1,host.docker.internal
        ```
      * Copy the user settings template: `cp user_settings.yaml.example user_settings.yaml`
      * Edit `user_settings.yaml` to bind your desired models to core specialists like the `router_specialist`.

3.  **Build and Run the Containers**
    From the project root, run the following command. This will build the Docker image, start the application and proxy containers, and run them in the background.

    ```bash
    docker compose up --build -d
    ```

### How to Interact (Docker)

  * **Web UI (Gradio):** Access the web interface in your browser at **`http://localhost:5003`**.
  * **V.E.G.A.S. Terminal:** A real-time, streaming terminal interface for monitoring agent execution at **`http://localhost:3000`**.
  * **API Docs (FastAPI):** Access the interactive API documentation at **`http://localhost:8000/docs`**.
  * **Command Line (CLI):** To interact via the CLI, execute the `cli.py` script inside the running `app` container.
    ```bash
    docker compose exec app python -m app.src.cli
    ```
    For multi-line input, pipe your prompt into the command:
    ```bash
    cat your_prompt.txt | docker compose exec -T app python -m app.src.cli
    ```

### Applying Configuration Changes

If you make changes to configuration files while the containers are running, you may need to restart the services for them to take effect.

  * **Changes to `.env`, `config.yaml`, or Python code:** Restart the `app` container.
    ```bash
    docker compose restart app
    ```
  * **Changes to `proxy/squid.conf`:** Restart the `proxy` container.
    ```bash
    docker compose restart proxy
    ```

-----

## Local Virtual Environment Setup (Alternative)

If you prefer not to use Docker, you can set up a local Python virtual environment.

### Prerequisites

  * Python 3.12+

### Installation & Setup

1.  Run the installation script for your OS from the project root (e.g., `./scripts/install.sh`). This creates a virtual environment and copies example configuration files.
2.  **Configure your environment.** Edit the newly created `.env` file to add your API keys and local model server URLs (e.g., `http://localhost:1234`).
3.  **Bind your models.** Open `user_settings.yaml` and specify which LLM providers you want to use.

### Running the Application

1.  **Start the API Server:**
    ```bash
    # On Linux/macOS:
    ./scripts/server.sh start

    # On Windows:
    .\scripts\server.bat start
    ```
2.  **Start the Web UI (in a separate terminal):**
    ```bash
    # First, activate the virtual environment
    source ./.venv_agents/bin/activate
    # Then, run the UI
    python -m app.src.ui --port 5003
    ```

## For Developers: Documentation & Next Steps

This scaffold is designed for serious agentic system development with comprehensive documentation:

### Essential Reading

  * **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)**: The central hub for all documentation.
  * **[System Architecture](./docs/ARCHITECTURE.md)**: Core concepts, patterns, and best practices.
  * **[Configuration Guide](./docs/CONFIGURATION_GUIDE.md)**: The 3-Tiered Configuration System.
  * **[MCP Guide](./docs/MCP_GUIDE.md)**: Synchronous service calls and the Message-Centric Protocol.
  * **[Observability Guide](./docs/OBSERVABILITY.md)**: LangSmith integration and debugging.
  * **[Creating a New Specialist](./docs/CREATING_A_NEW_SPECIALIST.md)**: Step-by-step tutorial for adding custom specialists.
  * **[Integration Test Guide](./docs/INTEGRATION_TEST_GUIDE.md)**: Patterns and examples for writing integration tests.
  * **[Graph Construction Guide](./docs/GRAPH_CONSTRUCTION_GUIDE.md)**: Subgraph patterns and workflow composition

### Observability (Critical for Development)

Debugging complex multi-agent interactions with `print` statements is insufficient. This scaffold integrates with **LangSmith** out of the box for:
  * Visual tracing of every run (hierarchical specialist execution)
  * State inspection at each step
  * Error isolation with red highlighting
  * Token count and latency tracking

**Setup**: Add LangSmith credentials to `.env` and ensure the FastAPI `lifespan` manager is present (see [Observability Guide](./docs/OBSERVABILITY.md)).

### Current Status

**Maturity**: Alpha / Active Development
**Roadmap Progress**: Project Bedrock 100% complete (37/37 tasks)
**Test Coverage**: 1,000+ tests across unit, integration, and contract testing

**Production-Ready Features:**
- Tiered Chat Subgraph (CORE-CHAT-002) with parallel progenitors
- MCP Infrastructure (internal + external containerized services)
- Fail-Fast Validation (startup + route validation)
- Invariant Monitor & Circuit Breaker system
- Context Engineering pipeline (Triage → Facilitate → Execute)
- Hybrid Routing Engine (declarative + procedural + probabilistic)
- V.E.G.A.S. Terminal UI for real-time streaming
- surf-mcp integration for browser automation

**Post-Bedrock Development:**
- ReActMixin for iterative tool-use patterns
- Deep Research pipeline
- Tiered synthesis with graceful degradation

See [docs/ADRs/](./docs/ADRs/) for architectural decisions and design documentation.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

© 2025 [Reflective Attention](http://reflectiveattention.ai/)
