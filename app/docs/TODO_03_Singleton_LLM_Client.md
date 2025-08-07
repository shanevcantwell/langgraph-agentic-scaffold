# TODO: Implement Singleton Pattern for LLMClientFactory

## Objective
Refactor the `LLMClientFactory` in `src/llm/factory.py` to ensure only one instance of each LLM client (e.g., `GeminiClient`, `OllamaClient`) is created during the application's entire lifecycle.

## Rationale
Currently, each specialist creates its own `LLMClient` instance upon initialization. This is highly inefficient, wasting memory and potentially causing redundant API authentications. A Singleton pattern will centralize client management and ensure resources are shared.

## Step-by-Step Plan

1.  **Open the file:** `src/llm/factory.py`.
2.  **Locate the class:** `LLMClientFactory`.
3.  **Add a private class-level dictionary** to store client instances. This dictionary will act as a registry or cache.
    ```python
    class LLMClientFactory:
        _instances: Dict[str, BaseLLMClient] = {}
        # ... rest of the class
    ```
4.  **Modify the `create_client` method.** The current implementation creates a new client on every call. The new logic must first check the `_instances` registry.
    *   **Check the registry:** Before any `if/elif` blocks, check if the `provider` key already exists in `LLMClientFactory._instances`.
    *   **Return existing instance:** If it exists, return the stored client instance immediately: `return LLMClientFactory._instances[provider]`.
    *   **Create and store new instance:** If it does not exist, proceed with the existing `if/elif` logic to create the new client. **Crucially**, before returning the new client, store it in the registry: `LLMClientFactory._instances[provider] = new_client`.

## Definition of Done
To verify the change, run the application using `python -m src.main`. Observe the console output at startup. The "---INITIALIZED ... CLIENT---" message for any given provider (e.g., Gemini) should appear **only once**, no matter how many specialists are initialized. The previous behavior showed this message multiple times.
