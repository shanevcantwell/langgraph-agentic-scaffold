# PROPOSAL: Refactor to a Singleton LLM Client

## Objective
To refactor the application's architecture to ensure that only one instance of the `ChatGoogleGenerativeAI` client is created and shared across all specialists for the duration of the application's lifecycle.

## Rationale
The current architecture, where each specialist potentially instantiates its own LLM client, is inefficient and difficult to maintain. This leads to:
1.  **Performance Overhead:** Unnecessary object creation and potential re-authentication for each specialist call.
2.  **Configuration Drift:** The risk of different specialists being initialized with slightly different model parameters (temperature, model name, etc.), leading to inconsistent behavior.
3.  **Observability Challenges:** It is significantly more complex to attach a single, consistent trace (e.g., with LangSmith) to multiple, ephemeral client instances.

Centralizing the client into a Singleton pattern is a foundational prerequisite for both the **Observability Integration** and **Agentic Loops** proposals. It is a critical cleanup and stabilization step.

## Architectural Vision
We will implement a factory or a shared module pattern. A single module (e.g., `src/clients.py`) will be responsible for initializing the `ChatGoogleGenerativeAI` client once, loading configuration from environment variables. All specialist nodes will then import and use this pre-initialized instance.

This change will be verified by running the existing unit test suite, which should continue to pass, confirming that the refactoring has not introduced any regressions.
