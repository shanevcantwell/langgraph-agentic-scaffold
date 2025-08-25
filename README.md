# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.

## **Code in this branch works as described in docs/DEVELOPERS_GUIDE.md and other provided documents. Please report any issues that you have using this scaffold in the Issues tab.**

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
*   **Two-Stage Semantic Routing:** A sophisticated, two-stage routing system increases efficiency and robustness. An initial `Triage` specialist recommends relevant tools, allowing the main `Router` to make faster, more accurate, and cheaper routing decisions. This pattern also enables specialists to "self-correct" by recommending a different specialist if their own preconditions are not met.
*   **Schema-Enforced Reliability:** Utilizes Pydantic models to define "hard contracts" for LLM outputs. For supported providers, this guarantees that the LLM will return a valid JSON object matching your schema, dramatically reducing runtime errors and validation boilerplate.
*   **Wrapped Specialists:** Extend the system by wrapping external agents. A `WrappedSpecialist` base class allows you to integrate third-party agents into your workflow by implementing simple data translation methods.
*   **Modern Python Tooling:** Uses `pyproject.toml` for project definition and `pip-tools` to generate pinned `requirements.txt` files, ensuring reproducible and reliable builds for both production and development.
*   **Developer vs. User Configuration:** The scaffold makes a clear distinction between developer-level system definition (`config.yaml`) and potential end-user settings. `config.yaml` is a developer artifact for building the system; for a deployed application, a separate, more constrained configuration layer should be exposed to users.
*   **Model-Specific Prompts:** The configuration allows you to assign different prompt files to the same specialist based on the model it's using. This enables fine-tuning instructions for specific model families (e.g., a more verbose prompt for a smaller model, a different format for an OpenAI vs. a Gemini model) without code changes.

## ⚠️ A Critical Note on Security

This scaffold is designed for architectural exploration and grants significant power to the LLM. The tools you create can execute real code, access your file system, and make external API calls with your keys.

> [!WARNING]
> **You are granting the configured LLM direct control over these powerful tools.**
>
> Unlike a single model call, an agentic system can create feedback loops that **amplify** a simple misunderstanding over many iterations. This emergent behavior can lead to complex, unintended, and irreversible actions like file deletion or data exposure.
>
> With a nod to the model cards of [Eric Hartford (QuixiAI)](https://github.com/QuixiAI):
> > This system is your tool, an extension of your will. Just as you are personally responsible for what you do with a knife, gun, fire, car, or the internet, you are the creator and originator of any actions performed by the agents you build and run. You take full and sole responsibility for what you build.
>
> **Always run this project in a secure, sandboxed environment (like a Docker container or a dedicated VM).**

## Getting Started

### Prerequisites

*   Python 3.10+
*   Access to an LLM (e.g., Google AI Studio, OpenAI, or a local server like LM Studio or Ollama).

### Installation & Setup

To get started quickly, run the appropriate installation script for your operating system from the project root:

*   On **Linux/macOS**:
    ```sh
    ./scripts/install.sh
    ```
*   On **Windows**:
    ```bat
    .\scripts\install.bat
    ```

These scripts will:
*   Clone the repository (if not already cloned).
*   Create and activate a Python virtual environment.
*   Install all necessary Python dependencies.
*   Copy example configuration files (`.env.example` to `.env`, `config.yaml.example` to `config.yaml`).
*   Check for the `jq` command-line JSON processor (required for verification scripts) and provide installation instructions if missing.
*   For Windows, provide a note about PowerShell execution policy if running PowerShell scripts.

After running the installation script, remember to edit `.env` with your API keys and `config.yaml` to define your agent setup.
The server script (`scripts/server.py`) will automatically load the `.env` file into the environment when you run the `start` command.

5.  **Run the application:**
    Use the provided scripts to start the API server.
    *   On **Linux/macOS**:
        ```sh
        ./scripts/server.sh start
        ```
    *   On **Windows**:
        ```bat
        .\scripts/server.bat start
        ```
    Once running, you can access the interactive API documentation at **`http://127.0.0.1:8000/docs`**.

### Interact with the Agent via CLI

Once the server is running, you can send prompts to the agent using the command-line interface:

*   On **Linux/macOS**:
    ```sh
    ./scripts/cli.sh "Your prompt for the agent goes here."
    ```
*   On **Windows**:
    ```bat
    .\scripts\cli.bat "Your prompt for the agent goes here."
    ```

## Contributing

We welcome contributions from the community! If you're interested in helping improve the scaffold, please read our **Contributing Guide**. It contains our "Open Core" philosophy, development workflow, and guidelines for submitting pull requests.


## For Developers

This repository is designed to be a starting point for your own complex projects. For detailed information on the architecture, development protocols, and how to add your own specialists, please see the **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)** and the **[Creating a New Specialist Guide](./docs/CREATING_A_NEW_SPECIALIST.md)**.

To set up a full development environment with testing and linting tools, run:
```sh
pip install -r requirements-dev.txt
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.