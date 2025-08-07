# langgraph-agentic-scaffold

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A foundational scaffold for building multi-agent systems using LangGraph, featuring a modular "specialist" architecture.

## Core Concepts

*(This is your most important section. Briefly explain the "why" of your architecture.)*

This project is not a library but a **template** for structuring a complex agentic application. The core philosophy is to separate concerns into distinct components:

* **Graph (`/app/src/graph`):** Defines the state machine. It orchestrates the flow of logic and state between different nodes.
* **Specialists (`/app/src/llm/specialists`):** These are modular, role-based agents. Each specialist has a specific prompt and is responsible for a single, well-defined task (e.g., a "researcher" specialist, a "coder" specialist). The LLM acts as the **Reasoning Engine** for each specialist.
* **Tools (`/app/src/agents/tools`):** Concrete functions that the specialists can call to interact with the outside world (e.g., file I/O, API calls).

## Features

* **Modular Architecture:** Easily add or remove "specialist" agents.
* **Multi-LLM Support:** Client abstractions for Gemini, Ollama, and LM Studio.
* **Stateful Execution:** Leverages LangGraph to manage conversational state across multiple turns.
* **Configuration-driven:** Uses `.env` for secrets and API keys.

## Getting Started

### Prerequisites

* Python 3.11+
* Access to an LLM (e.g., via Google AI Studio, Ollama, or LM Studio running locally).

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/langgraph-agentic-scaffold.git](https://github.com/your-username/langgraph-agentic-scaffold.git)
    cd langgraph-agentic-scaffold
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure your environment:**
    ```bash
    # Copy the example .env file
    cp .env.example .env
    ```
    Now, edit the `.env` file to add your API keys and other settings.

4.  **Run the application:**
    ```bash
    # Example command to run the main graph
    python -m app.main
    ```

## Project Status & Disclaimer

This is a personal project posted as a public backup and architectural reference. It is not actively maintained, and I am not looking to provide support. Feel free to fork it, learn from it, and adapt it for your own purposes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
