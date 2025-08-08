
# PROPOSAL: Transition to a Tool-Based Architecture

## Objective
To refactor the current "monolithic specialist" design into a more flexible and scalable "tool-based" architecture, where a primary agent orchestrates a library of discrete tools.

## Rationale
The current model, where each node is a self-contained specialist, is rigid. A more modern and powerful architecture, as exemplified by the `deep_researcher`'s distinct `web_research` and `summarize_sources` nodes, involves an agent that can reason about and select from a set of available tools.

This transition will:
1.  **Increase Composability:** Tools can be easily mixed and matched to create new agent capabilities without writing new specialists from scratch.
2.  **Promote Reusability:** A `read_file` tool can be used by a research agent, a coding agent, or a summarization agent.
3.  **Align with Industry Standards:** This architecture directly leverages the native tool-calling capabilities of modern LLMs and aligns with frameworks like LangChain's agent executors.

## Architectural Vision
The implementation will be a phased refactoring:
1.  **Decomposition:** The methods within existing specialists (e.g., `FileSpecialist`) will be refactored into standalone functions decorated with LangChain's `@tool`.
2.  **Toolkit Creation:** These individual tools will be collected into a list or "toolkit."
3.  **Orchestrator Agent:** The primary graph logic will be replaced with a new "Orchestrator" agent. This agent will be initialized with the toolkit and will be responsible for interpreting the user's request and deciding which tool(s) to call in what sequence to achieve the objective. The current router logic will be superseded by the LLM's native tool-calling reasoning.
