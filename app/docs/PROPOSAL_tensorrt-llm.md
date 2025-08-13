# Architectural Blueprint: Provider Failover Mechanism

**1. Objective:**
   - To modify the system to automatically fall back to a secondary, local LLM provider in the event the primary, cloud-based provider is unavailable or times out.

**2. Architectural Pattern: Redundancy and Automated Failover**
   - The system will be configured with both a primary and a fallback provider.
   - The core logic will attempt to use the primary provider first.
   - Upon detection of a specific set of network-related or service availability errors, the system will automatically retry the request using the fallback provider.

**3. Component-Level Design Changes:**

   **A. Configuration (`.env` file):**
      - The configuration schema must be updated to support defining both providers.
      - **Required Variables:**
         - `LLM_PROVIDER_PRIMARY`: The primary choice (e.g., "gemini").
         - `LLM_PROVIDER_FALLBACK`: The secondary choice (e.g., "ollama", "lmstudio").
         - All necessary API keys and URLs for both providers must also be present (e.g., `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`).

   **B. LLM Client Factory (`src/llm/factory.py`):**
      - This component's responsibility will be expanded. It will not just create a single client, but will orchestrate the creation of a "Resilient Client."
      - **Action:** Modify the `get_llm_provider()` function (or create a new factory function) to:
         1. Read both `LLM_PROVIDER_PRIMARY` and `LLM_PROVIDER_FALLBACK` from the environment.
         2. Instantiate the client for the primary provider.
         3. Instantiate the client for the fallback provider.
         4. Pass both clients to a new `ResilientClient` wrapper class during its instantiation.
         5. Return the single `ResilientClient` instance.

   **C. Resilient LLM Client (New Component):**
      - A new wrapper class, `ResilientClient`, must be created. This class will encapsulate the failover logic. It will adhere to the same interface as the other LLM clients (i.e., it must have an `invoke` method).
      - **Location:** `src/llm/resilient_client.py`
      - **Constructor (`__init__`):**
         - Accepts two arguments: `primary_client` and `fallback_client`.
      - **Core Logic (`invoke` method):**
         1. Wrap the call to the primary client in a `try...except` block.
         2. `try`: `self.primary_client.invoke(messages)`
         3. `except`: The block must catch a specific, curated list of retryable exceptions (e.g., `google.api_core.exceptions.ServiceUnavailable`, `requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`). It should *not* catch all exceptions (e.g., a `400 Bad Request` is a user error, not a service failure, and should not trigger a failover).
         4. If a caught exception occurs:
            - Log a warning indicating that the primary provider failed and that a fallback is being attempted. This is critical for observability.
            - `return self.fallback_client.invoke(messages)`
         5. If the primary call succeeds, return its result directly.

   **D. Dependency Injection (`main.py`):**
      - No significant changes are required here, which demonstrates the strength of this design.
      - The `main.py` file will continue to call the `get_llm_provider()` factory. The factory will now return the `ResilientClient` instance.
      - This `ResilientClient` will be injected into the specialists. The specialists remain completely unaware of the failover logic; they simply call the `invoke` method on the provider they are given. The abstraction is maintained.

**4. Validation Criteria:**
   - When the primary provider (Gemini) is available, the system functions normally.
   - When the primary provider is made unavailable (e.g., by disconnecting from the internet or providing an invalid API key), the system logs a warning and successfully completes the workflow using the configured local fallback provider (Ollama/LM Studio).
