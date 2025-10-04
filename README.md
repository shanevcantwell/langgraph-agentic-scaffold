# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems

<img width="3407" height="2072" alt="LangGraph Agentic Scaffold Architecture Diagram" src="[https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1](https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1)" />

[](https://opensource.org/licenses/MIT)
[](https://www.python.org/downloads/)
[](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.

### 🎥 Video Briefings

| 5-Minute Developer Briefing | 90-Second Elevator Pitch |
| :---: | :---: |
| [](https://www.youtube.com/watch?v=KfqKRXvznDc) | [](http://reflectiveattention.ai/videos/Unlocking_Multi-Agent_AI__Elevator_Pitch_for_the_Langgraph-Agen.mp4) |
| A complete technical rundown of the scaffold's architecture, mission, and how to get started. | A concise, audio-only overview of the project's value proposition. |

## Mission & Philosophy

The mission is to provide a clear, maintainable, and testable template for constructing multi-agent systems. The core philosophy is a separation of concerns, where the system is composed of distinct agent types:

  * **Specialists (`BaseSpecialist`):** Modular agents that perform a single, well-defined task. The system supports both LLM-driven specialists for complex reasoning and deterministic "procedural" specialists for reliable, code-based actions.
  * **Runtime Orchestrator (`RouterSpecialist`):** A specialized agent that makes the turn-by-turn routing decisions *within* the running graph.
  * **Structural Orchestrator (`GraphBuilder`):** A high-level system component responsible for reading the configuration, instantiating all specialists, and compiling the final `LangGraph` instance before execution.

## Architectural Highlights

This scaffold provides a well-defined architecture designed for reliability and scalability.

  * **API-First Design:** The system is exposed via a FastAPI web server, providing a clean, modern interface for interaction and integration.
  * **Configuration-Driven:** The entire agentic system including specialists, models, and prompts, is defined in a central `config.yaml`. The system's structure is not dependent on changing any Python code.
  * **First-Class Observability:** Integrated with LangSmith out of the box. The architecture includes the necessary hooks to provide detailed, hierarchical traces of every agentic run, which is essential for debugging complex, multi-step interactions.
  * **Decoupled Adapter Pattern:** Specialists are decoupled from the underlying LLM clients. They request a pre-configured "adapter" by name, allowing you to swap LLM providers (Gemini, OpenAI, Ollama, etc.) in the config file without touching the specialist's business logic.
  * **Semantic Routing:** A `Triage` specialist recommends relevant tools, allowing the main `Router` to make faster and more accurate routing decisions.
  * **Schema-Enforced Reliability:** Utilizes Pydantic models to define "hard contracts" for LLM outputs, dramatically reducing runtime errors and validation boilerplate.
  * **Robust Termination Sequence:** Implements a mandatory three-stage finalization process, ensuring every workflow concludes with a predictable and observable shutdown sequence for enhanced reliability.
  * **Layered Configuration Model:** Utilizes a powerful three-tiered configuration system (`.env`, `config.yaml`, `user_settings.yaml`) that separates secrets, core architecture, and user preferences for clean customization.
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
      * **Crucially**, to connect to local model servers (like LM Studio or Ollama) running on your host machine, you must use the special `host.docker.internal` hostname.
      * Copy the proxy configuration: `cp proxy/squid.conf.example proxy/squid.conf`
        ```dotenv
        # .env
        # Use host.docker.internal to connect from the container to services on the host.
        LMSTUDIO_BASE_URL="http://host.docker.internal:1234/v1/"
        OLLAMA_BASE_URL="http://host.docker.internal:11434"
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

## For Developers: Debugging and Observability

This repository is designed for serious development. Debugging complex, multi-agent interactions with `print` statements is insufficient. We strongly recommend using **LangSmith** for observability.

For detailed instructions on how to enable LangSmith tracing and other architectural best practices, please see the **[Developer's Guide](https://www.google.com/search?q=./docs/DEVELOPERS_GUIDE.md)**.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

© 2025 [Reflective Attention](http://reflectiveattention.ai/)