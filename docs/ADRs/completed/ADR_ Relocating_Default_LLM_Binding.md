### **Relocating `default_llm_config` for Improved Clarity**

*   **Status:** Completed
*   **Date:** 2024-08-01
*   **Author:** Senior Systems Architect

### 1. Context

The `default_llm_config` key in `user_settings.yaml` currently resides at the top level, alongside `llm_providers` and `specialist_model_bindings`. While functional, this placement is not intuitive. The default binding is conceptually part of the "binding" process, which is primarily managed under `specialist_model_bindings`. Having it as a top-level sibling creates a flat structure that doesn't fully represent the logical relationship between the configuration keys. This can lead to confusion for new developers trying to understand the configuration hierarchy.

**Current `user_settings.yaml` Structure:**

```yaml
llm_providers:
  my_default_model:
    type: "gemini"
    api_identifier: "gemini-1.5-flash"

specialist_model_bindings:
  router_specialist: "my_router_model"

default_llm_config: 'my_default_model' # Top-level key
```

This structure was highlighted as feeling "not quite right" during development, as the default binding is logically a fallback for the specialist bindings.

### 2. Decision

We will propose relocating the `default_llm_config` key to be nested under the `specialist_model_bindings` dictionary, using a special, reserved key like `__default__`. This creates a clear, hierarchical grouping for all model binding-related configurations, making the file's structure more self-documenting.

**Proposed `user_settings.yaml` Structure:**

```yaml
llm_providers:
  my_default_model:
    type: "gemini"
    api_identifier: "gemini-1.5-flash"

specialist_model_bindings:
  __default__: 'my_default_model' # Nested default
  router_specialist: 'my_router_model'
```

### 3. Implementation Sketch

This change would require modifications to two key files:

1.  **`app/src/utils/config_schema.py`:** The `UserSettings` Pydantic model would be updated to remove the top-level `default_llm_config` field. The `specialist_model_bindings` dictionary would remain a `Dict[str, str]`, with the `__default__` key being handled by the loader logic rather than the schema.

2.  **`app/src/utils/config_loader.py`:** The `_merge_configs` method would be updated. Instead of `user_settings.get("default_llm_config")`, it would look for `user_settings.get("specialist_model_bindings", {}).get("__default__")`.

```python
# In app/src/utils/config_loader.py

# ... inside _merge_configs ...

# OLD
# bindings = user_settings.get("specialist_model_bindings") or {}
# default_binding = user_settings.get("default_llm_config")

# NEW
bindings = user_settings.get("specialist_model_bindings") or {}
default_binding = bindings.pop("__default__", None) # Safely extract the default

# ... rest of the logic remains largely the same ...
```

### 4. Consequences

#### 4.1. Positive

*   **Improved Intuitiveness:** The configuration becomes more logical and easier to understand. All binding-related settings are co-located.
*   **Reduced Top-Level Noise:** The root of `user_settings.yaml` becomes cleaner, with fewer top-level keys to manage.
*   **Enhanced Clarity:** The structure more accurately reflects that the default is a property of the binding system, not a global setting.

#### 4.2. Negative & Risks

*   **Breaking Change:** This is a breaking change for existing `user_settings.yaml` files. All users would need to update their configuration.
*   **Documentation Overhead:** All related documentation, including `user_settings.yaml.example` and developer guides, would need to be updated to reflect the new structure.
*   **Magic String:** Introduces a "magic string" (`__default__`) into the configuration. While common, this can be less discoverable than an explicit key if not well-documented.