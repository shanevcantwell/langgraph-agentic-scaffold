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

3.  **User configures Checkpointing (Optional):**
    ```yaml
    # user_settings.yaml
    checkpointing:
      enabled: false # Default: false. Set to true only for RECESS architecture.
    ```
    *   **Note:** Checkpointing is currently **disabled by default** (`false`) to prevent conflicts with asynchronous streaming endpoints. Enable only if you are working on the RECESS architecture and understand the `SqliteSaver` limitations.

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
# .env (for non-Docker usage)
WORKSPACE_PATH=workspace
```

```yaml
# docker-compose.yml (sets WORKSPACE_PATH=/workspace in container)
environment:
  - WORKSPACE_PATH=/workspace
volumes:
  - ./workspace:/workspace  # Same path in main app and filesystem-mcp
```

This pattern ensures path consistency across containers. The `./workspace` host directory is mounted at `/workspace` in both the main app and filesystem-mcp containers, eliminating path translation issues.

## 1.1 Distributed Inference (Multi-GPU Box Setup)

For advanced setups where you want to run different models on different machines (e.g., Router on an RTX-3090, Specialists on an RTX-8000), you can use **named server references**.

**Step 1: Define physical machines in `.env` (Tier 1)**
```bash
# Default server (fallback if no named server specified)
LMSTUDIO_BASE_URL=http://localhost:1234/v1

# Named servers - physical machine names mapped to URLs
# Format: "name1=url1,name2=url2" (uses = since URLs contain :)
LMSTUDIO_SERVERS="rtx3090=http://192.168.1.100:1234/v1,rtx8000=http://192.168.1.101:1234/v1,basement=http://192.168.1.102:1234/v1"
```

**Step 2: Reference physical machines in `user_settings.yaml` (Tier 3)**
```yaml
llm_providers:
  lmstudio_router:
    type: "lmstudio"
    server: "rtx3090"  # → fast GPU for routing
    api_identifier: "gpt-oss-20b"

  lmstudio_specialist:
    type: "lmstudio"
    server: "rtx8000"  # → bigger GPU for specialists
    api_identifier: "qwen3-30b"

  lmstudio_local:
    type: "lmstudio"
    # No server specified → falls back to LMSTUDIO_BASE_URL
    api_identifier: "gemma-3-12b"
```

**Key Points:**
- `.env` defines **hardware** (physical machine names) - stable, infrastructure-level
- `user_settings.yaml` defines **roles** (which provider uses which machine) - changes as you experiment
- Adding a new provider doesn't require touching `.env`
- Moving a workload to different hardware only changes `user_settings.yaml`
- Providers without a `server` field fall back to `LMSTUDIO_BASE_URL`

## 1.2 Schema Enforcement Control (#219)

LM Studio's llama.cpp backend uses GBNF grammar-constrained decoding to enforce JSON output structure. Some model families (notably gpt-oss with Harmony format) are incompatible with GBNF grammar because their response-format control tokens are blocked by the JSON grammar, producing garbled output.

**Per-model flag:**
```yaml
llm_providers:
  my_harmony_model:
    type: "lmstudio"
    api_identifier: "gpt-oss-20b"
    skip_schema_enforcement: true  # Disable GBNF grammar; parse JSON from text
```

When `skip_schema_enforcement: true`:
- `response_format` is NOT sent in API requests — no grammar-constrained decoding
- The model produces JSON from prompt instructions (schema shape is still described in system prompts)
- Harmony control tokens (`<|channel|>`, `<|constrain|>`, `<|message|>`, etc.) are automatically stripped before JSON parsing
- Falls back to robust `{`-to-`}` extraction if direct `json.loads()` fails

**Default:** `false` (grammar enforcement enabled). Only set `true` for models whose response format is incompatible with GBNF grammar.

**Note:** The `$schema` declaration was also removed from all generated JSON schemas (#218) — LM Studio 0.4+ rejects it as an invalid keyword, silently disabling logit masking.

## 2.0 Container Naming Convention

The `docker-compose.yml` file uses explicit container names (`langgraph-app` and `langgraph-proxy`). This is to prevent conflicts with other projects and to make the containers easily identifiable. It is strongly recommended not to change these names, as it can lead to unexpected behavior and orphaned containers.

## 3.0 Architecture Selection

The system supports multiple architectural patterns, controlled by the `architecture` flag in `user_settings.yaml`.

*   **`default`**: The classic Router-centric architecture. A central Router Specialist dispatches tasks to other specialists.
*   **`convening`**: The "Convening of the Tribes" architecture (ADR-CORE-023). A `TribeConductor` orchestrates a persistent "Heap" of context, using an `AgentRouter` for dispatch and a `SemanticFirewall` for safety.

**Example:**
```yaml
# user_settings.yaml
architecture: "convening" # Defaults to "default" if omitted
```

## 4.0 Startup Pre-Flight Checks

At startup, the system performs several layers of validation before accepting requests:

1. **Configuration Validation**: Verifies environment variables are set (e.g., `GOOGLE_API_KEY`, `LMSTUDIO_BASE_URL`)
2. **Critical Specialist Loading**: Ensures specialists listed in `workflow.critical_specialists` loaded successfully
3. **LLM Provider Connectivity**: Pings each bound LLM provider to verify network reachability

**Provider Connectivity Check:**

The system sends a simple "pong" request to each LLM provider that's bound to a specialist. This catches:
- Network/proxy issues blocking connections
- Misconfigured `base_url` or API endpoints
- Models that aren't loaded in LM Studio

Ping failures generate warnings but don't block startup (some providers may be optional). Check logs for messages like:
```
Provider 'lmstudio_router' ping OK (245.3ms)
Provider 'lmstudio_vision' failed ping: Connection refused
```

## 5.0 Specialist Menu Exclusions (ADR-CORE-053)

Control which specialists appear in triage menus via the `excluded_from` config field. This allows you to hide internal specialists (execution engines, subgraph nodes) from user-facing routing decisions without code changes.

### 5.1 The `excluded_from` Field

Add `excluded_from` to any specialist's config to prevent it from appearing in specified menus:

```yaml
# config.yaml
specialists:
  batch_processor_specialist:
    type: "llm"
    prompt_file: "batch_processor_prompt.md"
    description: "Internal execution engine for file operations..."
    # ADR-CORE-053: Hide from triage menus
    excluded_from:
      - triage_architect
      - prompt_triage_specialist
```

### 5.2 Exclusion Taxonomy

Three mechanisms control specialist visibility at different lifecycle stages:

| Pattern | When | Who Decides | Mechanism |
|---------|------|-------------|-----------|
| `excluded_from` (config) | Graph build time | Config author | Baked into specialist_map at construction |
| `forbidden_specialists` (ADR-016) | Runtime (loop detection) | InvariantMonitor | Checked per-turn via scratchpad |
| `decline_task` (ADR-016) | Runtime (self-assessment) | Specialist | Removed from recommendations |

### 5.3 Built-in Exclusions

Some specialists are always excluded from triage menus via `TRIAGE_INFRASTRUCTURE`:
- `router_specialist` - Central routing hub
- `archiver_specialist` - Workflow reports
- `end_specialist` - Termination and synthesis
- `critic_specialist` - Artifact review

These are defined in `specialist_categories.py` and cannot be overridden.

### 5.4 Adding Exclusions

To hide a specialist from triage's menu:

1. Add the `excluded_from` field to the specialist's config in `config.yaml`
2. List the triage specialists that should NOT see this specialist
3. Restart the container to rebuild the graph

**Example: Hiding an internal subgraph node**
```yaml
tiered_synthesizer_specialist:
  type: "procedural"
  description: "Combines progenitor responses..."
  excluded_from:
    - triage_architect
```

### 5.5 Future Extensibility

When creating a new menu-building specialist (e.g., `plan_specialist`):
1. Add `plan_specialist` to `excluded_from` lists for specialists that shouldn't appear
2. Query `self.exclusion_index.get("plan_specialist", set())` in configuration code

No code changes needed beyond config.yaml updates.

## 6.0 ReAct Loop Configuration

ProjectDirector (and any future react_step consumers) iteratively call tools via prompt-prix MCP until the task completes or a safeguard triggers. The loop is owned by each specialist directly — there is no shared mixin.

### 6.1 Max Iterations

Each specialist reads `max_iterations` from its own config block in `config.yaml`, falling back to a hardcoded default if absent.

```yaml
# config.yaml
specialists:
  project_director:
    type: "llm"
    max_iterations: 20  # Optional — overrides the code default (15)
    # ...
```

**Code defaults** (in `project_director.py`):
```python
DEFAULT_MAX_ITERATIONS = 15  # Used when config omits max_iterations
```

**Design rationale:** Stagnation detection (Section 6.2) is the primary safety valve, not arbitrary iteration limits. Low limits cause artificial boundaries that force complex cross-invocation continuity reconstruction. If the limit is reached, the specialist produces a partial synthesis with whatever progress was made and sets `max_iterations_exceeded: True` in artifacts.

### 6.2 Cycle Detection (Stagnation)

The ReAct loop detects when the LLM is stuck making the same tool calls repeatedly. This catches both:
- **Identical calls**: `list_directory(X)` → `list_directory(X)` → `list_directory(X)`
- **Cyclic patterns**: `read(A)` → `move(A)` → `read(A)` → `move(A)` (period 2, repeated)

**Configuration** (code-level class constant in `project_director.py`):
```python
CYCLE_MIN_REPETITIONS = 3  # Pattern must repeat this many times to trigger stagnation
```

- **Value of 2**: Aggressive detection, catches loops fast but may false-positive on legitimate batch operations
- **Value of 3** (default): Gives one "grace" repeat, better for file operations that naturally repeat patterns
- **Higher values**: More permissive, but wastes more tokens before detecting true stagnation

**When stagnation is detected**, the specialist:
1. Stops the loop immediately
2. Returns a message explaining what happened (`research_status: "stagnated"`)
3. Includes artifacts showing the tool history and the repeating pattern

### 6.3 Activity Tracking

PD writes `specialist_activity` to scratchpad — a list of human-readable strings summarizing filesystem mutations (create_directory, move_file, write_file, run_command). Facilitator curates this into an `accumulated_work` artifact that persists across passes, so PD on pass N sees operations from passes 1 through N-1.

The full react trace is captured to `scratchpad["react_trace"]` for observability (state_timeline, archive) but is NOT passed back to PD on retry. PD starts with a fresh trace each invocation (#170).

### 6.4 Tool Permissions

PD's available tools are declared in `config.yaml` under `tools:` — each entry maps an MCP service to the specific functions PD may call:

```yaml
specialists:
  project_director:
    tools:
      prompt-prix:
        - react_step
      filesystem:
        - list_directory
        - read_file
        - create_directory
        - move_file
      terminal:
        - run_command
        - get_cwd
        - get_allowed_commands
```

The model chooses which tools to call based on the tool schemas injected into the react_step prompt. Adding or removing tools here changes what PD can do without code changes.
