# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.

### An Open Core Project

`langgraph-agentic-scaffold` is an **Open Core** project, distributed under the permissive MIT license. We are committed to developing and maintaining this core as a powerful, free, and open-source foundation for the entire community. 

The goal of this public scaffold is to provide universally useful, un-opinionated tools and architectural best practices. This core also serves as the base for more advanced, proprietary applications which may include specialized agents, complex integrations, and unique user interfaces.

## Mission & Philosophy

The mission is to provide a clear, maintainable, and testable template for constructing multi-agent systems. The core philosophy is a separation of concerns, where the system is composed of two primary agent types:

*   **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code).
*   **Orchestrators:** High-level components that manage the workflow by compiling a `LangGraph` instance and routing tasks between the necessary Specialists.

## Architectural Highlights

This scaffold is not just a collection of scripts; it's a well-defined architecture designed for reliability and scalability.

*   **API-First Design:** The system is exposed via a **FastAPI** web server, providing a clean, modern interface for interaction and integration. Includes auto-generated interactive documentation (via Swagger UI).
*   **Configuration-Driven:** The entire agentic system's specialists, models, and prompts is defined in a central `config.yaml`. The system's structure is not dependent on changing any Python code.
*   **Decoupled Adapter Pattern:** Specialists are decoupled from the underlying LLM clients. They request a pre-configured "adapter" by name, allowing you to swap LLM providers (Gemini, OpenAI, Ollama, etc.) in the config file without touching the specialist's business logic.
*   **Schema-Enforced Reliability:** Utilizes Pydantic models to define "hard contracts" for LLM outputs. For supported providers, this guarantees that the LLM will return a valid JSON object matching your schema, dramatically reducing runtime errors and validation boilerplate.
*   **Wrapped Specialists:** Extend the system by wrapping external agents. A `WrappedSpecialist` base class allows you to integrate third-party agents into your workflow by implementing simple data translation methods.
*   **Modern Python Tooling:** Uses `pyproject.toml` for project definition and `pip-tools` to generate pinned `requirements.txt` files, ensuring reproducible and reliable builds for both production and development.
*   **Model-Specific Prompts:** The configuration allows you to assign different prompt files to the same specialist based on the model it's using. This enables fine-tuning instructions for specific model families (e.g., a more verbose prompt for a smaller model, a different format for an OpenAI vs. a Gemini model) without code changes.

## ⚠️ A Critical Note on Security

This scaffold is designed for architectural exploration and grants significant power to the LLM. The tools you create can execute real code, access your file system, and make external API calls with your keys.

**You are granting the configured LLM direct control over these powerful tools.**

Any LLM at any time can interpret your requests in unexpected ways. Be mindful of what you are turning control over to an emergent property of statistical math. Anything the code you turn over control can do, the LLM will be able to perform. This includes such irreversible actions as file deletion, data exposure, or unintended resource usage. An agentic system allows complicated narratives to form as specialists interact, creating indefinite numbers of calls to inference that can amplify a mistaken understanding. Treat this system with the same caution you would a loaded weapon. You take full and sole responsibility for what you build and run with it.

**Always run this project in a secure, sandboxed environment (like a Docker container or a dedicated VM).**

## Getting Started

### Prerequisites

*   Python 3.10+
*   Access to an LLM (e.g., via Google AI Studio, OpenAI, or a local server like Ollama).

### Installation & Setup

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/shanevcantwell/langgraph-agentic-scaffold.git
    cd langgraph-agentic-scaffold
    ```

2.  **Create and activate a virtual environment:**
    *   For **Linux/macOS**:
        ```sh
        python3 -m venv .venv_agents
        source ./.venv_agents/bin/activate
        ```
    *   For **Windows**:
        ```sh
        python -m venv .venv_agents_windows
        .\.venv_agents_windows\Scripts\activate
        ```

3.  **Install dependencies:**
    This command installs the exact versions of all packages needed to run the application.
    ```sh
    pip install -r requirements-dev.txt
    ```

4.  **Configure your environment:**
    Copy the example configuration files.
    ```sh
    # Copy the example .env file for secrets
    cp .env.example .env

    # Copy the example app config file
    cp config.yaml.example config.yaml
    ```
    Now, edit `.env` with your API keys and `config.yaml` to define your agent setup.

5.  **Run the application:**
    Use the provided scripts to start the API server.
    *   On **Linux/macOS**:
        ```sh
        ./run.sh start
        ```
    *   On **Windows**:
        ```bat
        .\windows_run.bat
        ```
    Once running, you can access the interactive API documentation at **`http://127.0.0.1:8000/docs`**.

## For Developers

This repository is designed to be a starting point for your own complex projects. For detailed information on the architecture, development protocols, and how to add your own specialists, please see the **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)** and the **[Creating a New Specialist Guide](./docs/CREATING_A_NEW_SPECIALIST.md)**.

To set up a full development environment with testing and linting tools, run:
```sh
pip install -r requirements-dev.txt
```

Once the server is running, you can interact with it from a separate terminal using the CLI script:
```sh
python app/src/cli.py "Your prompt for the agent goes here."
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.