# Contributing to langgraph-agentic-scaffold

First off, thank you for considering contributing! This project thrives on community involvement, and we welcome any contributions that help make this scaffold a better starting point for everyone.

## The "Open Core" Philosophy

This project is the "core" in an [Open Core](https://en.wikipedia.org/wiki/Open-core_model) model. Our goal is to build a robust, generic, and un-opinionated foundation for creating agentic systems. When contributing, please keep this philosophy in mind. We are looking for contributions that are:

*   **Generic and Widely Applicable:** New tools or specialists should be useful in a wide variety of agentic systems, not tied to a specific product or niche use case.
*   **Modular and Extensible:** Code should be designed to be easily understood, replaced, or extended.
*   **Best Practices:** Contributions should reflect modern Python standards and demonstrate best practices for working with LangGraph.

Specialized features, complex UI components, or integrations with specific proprietary services are generally better suited for separate projects that build upon this scaffold.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue and provide as much detail as possible, including:
*   A clear and descriptive title.
*   Steps to reproduce the bug.
*   Expected behavior and what happened instead.
*   Your environment (Python version, OS, etc.).

### Suggesting Enhancements

If you have an idea for a new feature or an improvement to an existing one, please open an issue to discuss it first. This allows us to ensure the proposed change aligns with the project's philosophy before you put in the work.

### Submitting Pull Requests

1.  Fork the repository and create a new branch from `main`.
2.  Make your changes. Ensure your code follows the existing style and includes tests where appropriate.
3.  Update the documentation if your changes affect it.
4.  Ensure all tests pass by running `pytest`.
5.  Open a pull request with a clear description of your changes and why they are needed.

## Development Workflow

This project uses `pip-tools` to manage dependencies. If you add or change a dependency in `pyproject.toml`, please run the sync script to update the `requirements.txt` files and include them in your pull request.
*   **Linux/macOS:** `./scripts/sync-reqs.sh`
*   **Windows:** `.\scripts\sync-reqs.bat`

Thank you for helping us build the best possible scaffold for agentic systems!