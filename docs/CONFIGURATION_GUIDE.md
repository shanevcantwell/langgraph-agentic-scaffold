# Configuration Guide

## 1.0 The 3-Tiered Configuration System

The system's configuration is a three-tiered hierarchy. Understanding this model is essential for both running and extending the system. The layers are resolved at startup by the `ConfigLoader`.

**Tier 1: Secrets (`.env`)**
*   **File:** `.env`
*   **Purpose:** Provides raw secrets and environment-specific connection details (e.g., `GOOGLE_API_KEY`, `LMSTUDIO_BASE_URL`).
*   **Git:** Ignored.

**Tier 2: Architectural Blueprint (`config.yaml`)**  
*   **File:** `config.yaml`
*   **Purpose:** The system's architectural source of truth, managed by the developer. It defines all possible components (specialists) and the workflow structure. It is a pure blueprint of *what* the system can do, but not *how* it does it.
*   **Git:** Committed to source control.

**Tier 3: User Implementation (`user_settings.yaml`)**  
*   **File:** `user_settings.yaml`
*   **Purpose:** Defines the concrete implementation of the system for a given environment. While the file can be absent, a functional system **requires** it to define LLM providers and bind them to specialists. It is the single source of truth for:
    1.  Defining and naming all LLM provider configurations (`llm_providers`). This is where you specify which models to use (e.g., `gemini-2.5-pro`) and what to call them (e.g., `my_strong_model`).
    2.  Binding specialists to those providers (`specialist_model_bindings`).
    3.  Setting a system-wide default model (`default_llm_config`).
*   **Git:** Ignored.

**Example of Merging Logic:**

1.  **Developer defines the architecture in `config.yaml` (no providers here):**
    ```yaml
    # config.yaml
    specialists:
      router_specialist:
        type: "llm"
        # ...
      web_builder:
        type: "llm"
        # ...
    ```

2.  **User defines providers and bindings in `user_settings.yaml`:**
    ```yaml
    # user_settings.yaml
    default_llm_config: "my_fast_model"

    llm_providers:
      my_strong_model:
        type: "gemini"
        api_identifier: "gemini-1.5-pro-latest"
      my_fast_model:
        type: "gemini"
        api_identifier: "gemini-1.5-flash-latest"

    specialist_model_bindings:
      router_specialist: "my_strong_model"
    ```

3.  **Result:** At runtime, the `GraphBuilder` will instantiate the `router_specialist` and, seeing the binding in `user_settings.yaml`, will configure it to use the `my_strong_model` provider. The `web_builder` specialist, having no specific binding, will fall back to using the `my_fast_model` provider as defined by `default_llm_config`.

**Environment Variable Interpolation:**

Configuration files support environment variable substitution using the `${VAR_NAME}` syntax. This allows for single-source-of-truth configuration in `.env` files.

**Supported Syntax:**
- `${VAR_NAME}`: Required environment variable (raises error if not set)
- `${VAR_NAME:-default_value}`: Optional environment variable with fallback default

**Example - Workspace Path Coordination:**

```yaml
# config.yaml
specialists:
  file_specialist:
    root_dir: "${WORKSPACE_PATH:-workspace}"
```

```bash
# .env
WORKSPACE_PATH=workspace
```

```yaml
# docker-compose.yml
volumes:
  - app_workspace:/app/${WORKSPACE_PATH:-workspace}
```

This pattern ensures the FileSpecialist sandbox boundary, ConfigLoader path validation, and Docker volume mount all coordinate through a single definition in `.env`. Without env var interpolation, these three layers would be independent sources of truth that could drift out of sync.

## 2.0 Container Naming Convention

The `docker-compose.yml` file uses explicit container names (`langgraph-app` and `langgraph-proxy`). This is to prevent conflicts with other projects and to make the containers easily identifiable. It is strongly recommended not to change these names, as it can lead to unexpected behavior and orphaned containers.
