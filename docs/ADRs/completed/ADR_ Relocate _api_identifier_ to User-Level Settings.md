### **ADR: Relocate `api_identifier` to User-Level Settings**

*   **Status:** Completed
*   **Date:** 2025-09-17
*   **Deciders:** System Architecture Team

---

#### **1. Context**

The current configuration model, defined in `config.yaml.example` (Source: Configuration Example) and `PROJECT_STRUCTURE.md` (Source: PROJECT_STRUCTURE.md), places the `api_identifier` field within the `llm_providers` section of `config.yaml`.

This field specifies the exact model file or tag used by a local provider (e.g., LM Studio's GGUF filename, Ollama's model tag). This information is specific to a user's local machine setup.

This design has two primary flaws:
1.  **Security Risk:** Committing `config.yaml` to a shared repository leaks information about the specific models used in development, which could be a vector for targeted attacks. In future use cases with fine-tuned private models, this could leak sensitive model identifiers.
2.  **Developer Friction:** It forces every developer on a team to either constantly edit a tracked file (creating merge conflicts) or maintain their own divergent version of `config.yaml`, defeating its purpose as a common architectural blueprint.

This violates the core principle that `config.yaml` should define the *what* (the available provider types and their abstract settings) while `user_settings.yaml` should define the *how* (which specific models and keys the user wants to bind to those providers).

#### **2. Decision**

The `api_identifier` field will be **removed** from the `llm_providers` section of `config.yaml` and **moved** into `user_settings.yaml`.

The `user_settings.yaml` will be enhanced to not only bind specialists to providers but also to specify the concrete model for each provider configuration.

**2.1. New Configuration Structure**

**BEFORE (`config.yaml`):**

```yaml
llm_providers:
  lmstudio_router:
    type: "lmstudio"
    # This is the problematic field
    api_identifier: "openai/gpt-oss-20b-gguf/router-gpt-oss-20b-mxfp4.gguf"
    context_window: 8192
```

**AFTER (`config.yaml`):**

```yaml
# config.yaml (The Blueprint)
llm_providers:
  # Defines the 'shape' of the provider, but not the specific model
  lmstudio_router:
    type: "lmstudio"
    context_window: 8192
    # api_identifier is now GONE from here
```

**AFTER (`user_settings.yaml`):**

```yaml
# user_settings.yaml (The User's Environment)

# New section for defining the user's specific model for each provider
provider_models:
  lmstudio_router:
    api_identifier: "openai/gpt-oss-20b-gguf/router-gpt-oss-20b-mxfp4.gguf"
  lmstudio_specialist:
    api_identifier: "gemma-3-27b-it-abliterated@q8_0"
  gemini_pro:
    api_identifier: "gemini-1.5-pro"

# Existing section remains the same
specialist_model_bindings:
  router_specialist: "lmstudio_router"
  systems_architect: "gemini_pro"
```

**2.2. Implementation Impact**

The `ConfigLoader` utility will be updated. Its responsibility is to merge these two files into the final, unified configuration object that the rest of the application uses.

The updated merge logic will be:
1.  Load the base `config.yaml`.
2.  Load `user_settings.yaml`.
3.  Iterate through the `provider_models` section in `user_settings.yaml`.
4.  For each entry, inject the `api_identifier` into the corresponding `llm_providers` entry in the main config object.
5.  Proceed with the existing `specialist_model_bindings` logic.

The `AdapterFactory` and the adapters themselves will require no changes, as they receive the final, merged configuration from the `ConfigLoader`.

The example files (`config.yaml.example`, `user_settings.yaml.example`) and any relevant developer documentation must be updated to reflect this new, more secure structure.

---

#### **3. Consequences**

**Positive:**

*   **Improved Security:** User-specific model identifiers are no longer committed to source control.
*   **Correct Separation of Concerns:** The blueprint (`config.yaml`) is now properly decoupled from the local environment (`user_settings.yaml`).
*   **Reduced Developer Friction:** Eliminates merge conflicts and confusion related to local model configurations.
*   **Increased Flexibility:** A user can now easily define multiple configurations in `config.yaml` (e.g., `lmstudio_large`, `lmstudio_small`) and choose which specific model file to use for each in their private settings.

**Negative:**

*   This is a **breaking change** for existing configurations. All users will need to update their `user_settings.yaml` files to the new format.
*   The `ConfigLoader`'s logic becomes slightly more complex, as it now has to perform a deeper merge on the provider configurations. This is a negligible complexity increase for a significant architectural improvement.