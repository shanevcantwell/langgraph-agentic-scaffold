# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems
<img width="3407" height="2072" alt="{7A7E1E82-D24D-4B02-B03D-502688DD7B49}" src="https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1" />

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.

## Mission & Philosophy

The mission is to provide a clear, maintainable, and testable template for constructing multi-agent systems. The core philosophy is a separation of concerns, where the system is composed of two primary agent types:

*   **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code).
*   **Orchestrators:** High-level components that manage the workflow by compiling a `LangGraph` instance and routing tasks between the necessary Specialists.

## Architectural Highlights

This scaffold is not just a collection of scripts; it's a well-defined architecture designed for reliability and scalability.

*   **API-First Design:** The system is exposed via a **FastAPI** web server, providing a clean, modern interface for interaction and integration.
*   **Configuration-Driven:** The entire agentic system—its specialists, models, and prompts—is defined in a central `config.yaml`. The system's structure is not dependent on changing any Python code.
*   **First-Class Observability:** Integrated with **LangSmith** out of the box. The architecture includes the necessary hooks to provide detailed, hierarchical traces of every agentic run, which is essential for debugging complex, multi-step interactions.
*   **Decoupled Adapter Pattern:** Specialists are decoupled from the underlying LLM clients. They request a pre-configured "adapter" by name, allowing you to swap LLM providers (Gemini, OpenAI, Ollama, etc.) in the config file without touching the specialist's business logic.
*   **Two-Stage Semantic Routing:** A sophisticated routing system increases efficiency and robustness. An initial `Triage` specialist recommends relevant tools, allowing the main `Router` to make faster, more accurate, and cheaper routing decisions.
*   **Schema-Enforced Reliability:** Utilizes Pydantic models to define "hard contracts" for LLM outputs, dramatically reducing runtime errors and validation boilerplate.
*   **Modern Python Tooling:** Uses `pyproject.toml` and `pip-tools` to ensure reproducible and reliable builds for both production and development.

## ⚠️ A Critical Note on Security

This scaffold is designed for architectural exploration and grants significant power to the LLM. The tools you create can execute real code, access your file system, and make external API calls with your keys.

> [!WARNING]
> **You are granting the configured LLM direct control over these powerful tools.**
>
> An agentic system can create feedback loops that **amplify** a simple misunderstanding over many iterations. This emergent behavior can lead to complex, unintended, and irreversible actions like file deletion or data exposure.
>
> **Always run this project in a secure, sandboxed environment (like a Docker container or a dedicated VM).**

## Getting Started

### Prerequisites

*   Python 3.10+
*   Access to an LLM (e.g., Google Gemini API, LM Studio open weights models. Coming soon: OpenAI, Ollama).

### Installation & Setup

To get started, run the appropriate installation script for your operating system from the project root:

*   On **Linux/macOS**: `./scripts/install.sh`
*   On **Windows**: `.\scripts\install.bat`

These scripts will create a virtual environment, install dependencies, and copy example configuration files. After running the script, remember to edit `.env` with your API keys.

### Running the Application

Use the provided scripts to start the API server.
*   On **Linux/macOS**: `./scripts/server.sh start`
*   On **Windows**: `.\scripts\server.bat start`

Once running, you can access the interactive API documentation at **`http://127.0.0.1:8000/docs`**.

### Interact with the Agent via CLI

Once the server is running, you can send prompts to the agent using the command-line interface.

**For multi-line input (recommended):**
Simply run the script without arguments. You can then paste your prompt and press `Ctrl+D` (Linux/macOS) or `Ctrl+Z` then `Enter` (Windows) to submit.
*   On **Linux/macOS**: `./scripts/cli.sh`
*   On **Windows**: `.\scripts\cli.bat`

**For single-line input:**
You can still pass the prompt as a single, quoted string.
*   On **Linux/macOS**: `./scripts/cli.sh "Your prompt for the agent goes here."`
*   On **Windows**: `.\scripts\cli.bat "Your prompt for the agent goes here."`

## For Developers: Debugging and Observability

This repository is designed for serious development. Debugging complex, multi-agent interactions with `print` statements is insufficient. We strongly recommend using **LangSmith** for observability.

For detailed instructions on how to enable LangSmith tracing and other architectural best practices, please see the **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)**.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
