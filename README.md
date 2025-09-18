# langgraph-agentic-scaffold: An Open Core Scaffold for Agentic Systems
<img width="3407" height="2072" alt="LangGraph Agentic Scaffold Architecture Diagram" src="https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1" />

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A foundational scaffold for building robust, modular, and scalable multi-agent systems using LangGraph. This project provides a production-ready architecture that moves beyond simple scripts to a fully-fledged, API-driven application. It is designed to be the best possible starting point for any LangGraph-based agentic system.
 
> **[Watch the 5-Minute Video Briefing](https://reflectiveattention.ai/scaffold-briefing)** (External Link)

### 🎥 Video Briefings

| 5-Minute Developer Briefing | 90-Second Elevator Pitch |
| :---: | :---: |
| [![Watch the 5-Minute Briefing](https://github.com/user-attachments/assets/0bf289cf-da47-48d5-b0b9-ce54fd72486d)](./videos/langgraph-agentic-scaffold.mp4) | [![Listen to the 90-Second Pitch](https://github.com/user-attachments/assets/155d60bc-be1c-4508-a46c-341bdebfd69c)](http://reflectiveattention.ai/videos/Unlocking_Multi-Agent_AI__Elevator_Pitch_for_the_Langgraph-Agen.mp4) |
| A complete technical rundown of the scaffold's architecture, mission, and how to get started. | A concise, audio-only overview of the project's value proposition. |

## Mission & Philosophy

The mission is to provide a clear, maintainable, and testable template for constructing multi-agent systems. The core philosophy is a separation of concerns, where the system is composed of two primary agent types:

*   **Specialists:** Functional, LLM-driven components that perform a single, well-defined task (e.g., writing to a file, generating code).
*   **Orchestrators:** High-level components that manage the workflow by compiling a `LangGraph` instance and routing tasks between the necessary Specialists.

## Architectural Highlights

This scaffold provides a well-defined architecture designed for reliability and scalability.

*   **API-First Design:** The system is exposed via a **FastAPI** web server, providing a clean, modern interface for interaction and integration.
*   **Configuration-Driven:** The entire agentic system including specialists, models, and prompts, is defined in a central `config.yaml`. The system's structure is not dependent on changing any Python code.
*   **First-Class Observability:** Integrated with **LangSmith** out of the box. The architecture includes the necessary hooks to provide detailed, hierarchical traces of every agentic run, which is essential for debugging complex, multi-step interactions.
*   **Decoupled Adapter Pattern:** Specialists are decoupled from the underlying LLM clients. They request a pre-configured "adapter" by name, allowing you to swap LLM providers (Gemini, OpenAI, Ollama, etc.) in the config file without touching the specialist's business logic.
*   **Semantic Routing:** A `Triage` specialist recommends relevant tools, allowing the main `Router` to make faster and more accurate routing decisions.
*   **Schema-Enforced Reliability:** Utilizes Pydantic models to define "hard contracts" for LLM outputs, dramatically reducing runtime errors and validation boilerplate.
*   **Modern Python Tooling:** Uses `pyproject.toml` and `pip-tools` to ensure reproducible and reliable builds for both production and development.

## ⚠️ A Critical Note on Security

This scaffold grants significant power to one or more LLMs that you define as specialists. The tools you create can execute real code, access your file system, and make external API calls with your keys.

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
You can pass the prompt as a single, quoted string.
*   On **Linux/macOS**: `./scripts/cli.sh "Your prompt for the agent goes here."`
*   On **Windows**: `.\scripts\cli.bat "Your prompt for the agent goes here."`
 
## For Developers: Debugging and Observability

This repository is designed for serious development. Debugging complex, multi-agent interactions with `print` statements is insufficient. We strongly recommend using **LangSmith** for observability.

For detailed instructions on how to enable LangSmith tracing and other architectural best practices, please see the **[Developer's Guide](./docs/DEVELOPERS_GUIDE.md)**.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
