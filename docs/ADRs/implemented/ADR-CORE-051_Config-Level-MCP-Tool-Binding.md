# ADR-CORE-051: Config-Level MCP Tool Binding

**Status:** Implemented (2026-02-18 audit). `tools:` config blocks per specialist in config.yaml. Referenced as ADR-CORE-051 in navigator, text_analysis, exit_interview configs.
**Date:** 2026-01-25
**Deciders:** Shane
**Context:** Tool access is currently defined in specialist code, not config
**Supersedes:** N/A
**Relates To:** ADR-CORE-035 (Filesystem Architecture), ADR-MCP-003 (External MCP Integration)

---

## Context

Currently, MCP tool access is **code-level**, not **config-level**:

1. `GraphBuilder.initialize_external_mcp()` injects `external_mcp_client` to ALL specialists
2. Whether a specialist actually uses it depends entirely on its Python code
3. There's no config-level visibility or control over which tools each specialist can access

This creates several problems:

| Problem | Impact |
|---------|--------|
| No visibility | Config doesn't show what tools a specialist has |
| No granularity | Can't give read-only access (e.g., `read_file` yes, `write_file` no) |
| No guardrails | Any specialist could call any MCP tool if developer adds the code |
| Prompt drift | LLM might be told about tools the specialist can't actually use |

### Current State (Code-Level)

```python
# batch_processor_specialist.py - has filesystem access because code calls it
def _call_filesystem_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> str:
    result = sync_call_external_mcp(self.external_mcp_client, "filesystem", tool_name, arguments)

# triage_architect.py - has NO filesystem access (no code calling external_mcp_client)
# But external_mcp_client is still injected! No enforcement.
```

---

## Decision

Define MCP tool permissions per specialist in `config.yaml`. Enforce at runtime via `PermissionedMcpClient` wrapper.

### Proposed Config Schema

```yaml
specialists:
  triage_architect:
    type: "llm"
    prompt_file: "triage_architect_prompt.md"
    description: "..."
    tags: ["planning", "context_engineering"]
    tools:
      filesystem:
        - directory_tree
        - read_file
      # No write_file, move_file, edit_file = read-only access

  facilitator_specialist:
    type: "procedural"
    description: "..."
    tools:
      filesystem:
        - directory_tree
        - read_file
        - list_directory
      # Context gathering is read-only

  batch_processor_specialist:
    type: "llm"
    prompt_file: "batch_processor_prompt.md"
    description: "..."
    tools:
      filesystem:
        - read_file
        - write_file
        - create_directory
        - move_file
        - edit_file
        - get_file_info
        - directory_tree
      # Full CRUD access

  navigator_browser_specialist:
    type: "hybrid"
    description: "..."
    tools:
      navigator:
        - session_create
        - session_destroy
        - goto
        - click
        - type
        - read
        - snapshot
      # surf-mcp browser tools
```

### Alternative: Wildcard Syntax

```yaml
tools:
  filesystem: "*"  # All tools in this service

tools:
  filesystem:
    - "read_*"     # Pattern matching (read_file, read_multiple_files)
    - directory_tree
```

---

## Implementation

### 1. PermissionedMcpClient Wrapper

```python
# app/src/mcp/permissioned_client.py

class PermissionedMcpClient:
    """Wraps ExternalMcpClient with permission checking."""

    def __init__(self, inner_client: ExternalMcpClient, allowed_tools: Dict[str, List[str]]):
        """
        Args:
            inner_client: The actual MCP client
            allowed_tools: {"service_name": ["tool1", "tool2"]} or {"service_name": "*"}
        """
        self._inner = inner_client
        self._allowed_tools = allowed_tools

    def is_connected(self, service: str) -> bool:
        # Only report connected if specialist has ANY tools for this service
        if service not in self._allowed_tools:
            return False
        return self._inner.is_connected(service)

    def call_tool(self, service: str, tool: str, arguments: Dict[str, Any]) -> Any:
        allowed = self._allowed_tools.get(service, [])

        # Check wildcard
        if allowed == "*":
            return self._inner.call_tool(service, tool, arguments)

        # Check explicit list
        if tool not in allowed:
            # Return error message for LLM to self-correct, don't crash Python process
            return f"Permission Denied: Tool '{tool}' is not permitted for this specialist. Available tools on '{service}': {allowed}. Please adjust your plan."

        return self._inner.call_tool(service, tool, arguments)

    def get_available_tools(self, service: str) -> List[str]:
        """Returns only the tools this specialist is permitted to use."""
        allowed = self._allowed_tools.get(service, [])
        if allowed == "*":
            return self._inner.get_available_tools(service)
        return allowed
```

### 2. GraphBuilder Changes

```python
# app/src/workflow/graph_builder.py

async def initialize_external_mcp(self):
    # ... existing connection logic ...

    # NEW: Attach permissioned clients per specialist
    for name, instance in self.specialists.items():
        specialist_config = self.config.get("specialists", {}).get(name, {})
        tool_permissions = specialist_config.get("tools", {})

        if tool_permissions:
            # Specialist has explicit tool config - wrap with permissions
            instance.external_mcp_client = PermissionedMcpClient(
                self.external_mcp_client,
                allowed_tools=tool_permissions
            )
        else:
            # No tools config = no MCP access (or legacy behavior?)
            instance.external_mcp_client = None  # Option A: No access
            # instance.external_mcp_client = self.external_mcp_client  # Option B: Legacy full access
```

### 3. ReactEnabledSpecialist Wrapper

```python
# app/src/workflow/graph_builder.py (or new file)

class ReactEnabledSpecialist:
    """Wrapper that adds ReAct capability to any specialist via config."""

    def __init__(self, inner: BaseSpecialist, max_iterations: int, stop_on_error: bool):
        self._inner = inner
        self._max_iterations = max_iterations
        self._stop_on_error = stop_on_error

    def __getattr__(self, name):
        # Forward all attribute access to inner specialist
        return getattr(self._inner, name)

    # execute() delegates to inner - ReActMixin capability injected at runtime
```

**Config resolution with global defaults:**

```python
def _get_react_config(self, specialist_config: dict) -> Optional[ReactConfig]:
    react = specialist_config.get("react", {})
    if not react.get("enabled", False):
        return None

    global_defaults = self.config.get("react", {}).get("defaults", {})
    return ReactConfig(
        enabled=True,
        max_iterations=react.get("max_iterations", global_defaults.get("max_iterations", 10)),
        stop_on_error=react.get("stop_on_error", global_defaults.get("stop_on_error", False)),
    )
```

### 4. Config Schema

Add to `config_schema.py`:

```python
class ReactConfig(BaseModel):
    enabled: bool = False
    max_iterations: int = 10
    stop_on_error: bool = False

class SpecialistConfig(BaseModel):
    type: Literal["llm", "procedural", "hybrid"]
    tools: Optional[Dict[str, List[str]]] = None  # {"filesystem": ["read_file"]}
    react: Optional[ReactConfig] = None
    # ... existing fields ...
```

---

## Migration Path

**Single-phase implementation** (no legacy behavior):

1. Add `tools:` and `react:` support to config schema (`config_schema.py`)
2. Implement `PermissionedMcpClient` wrapper (`app/src/mcp/permissioned_client.py`)
3. Update GraphBuilder to:
   - Attach permissioned clients per specialist based on `tools:` config
   - Auto-inject tool descriptions into specialist prompts
   - Wrap specialists with `ReactEnabledSpecialist` based on `react:` config
4. Add `tools:` config to all specialists that use external MCP:
   - `batch_processor_specialist` → filesystem
   - `facilitator_specialist` → filesystem (read-only)
   - `navigator_browser_specialist` → navigator
5. Add `react:` config to specialists that need iteration
6. Remove `ReActMixin` class inheritance from `ProjectDirector`

**Breaking change:** Specialists without `tools:` config will have `external_mcp_client = None`. This is intentional - explicit is better than implicit.

---

## Decisions

### Q1: What about internal MCP (McpRegistry)?

**Decision: C) External MCP only.** Internal MCP (`mcp_client`) is trusted code for specialist-to-specialist calls. Lower risk, no enforcement needed.

### Q2: Tool discovery at startup?

**Decision: B) Runtime fail.** Defer startup validation - fail at runtime when tool is called. Simpler, matches current behavior. Can add startup introspection later.

### Q3: Default for missing `tools:` key?

**Decision: A) No access (secure default).** If a specialist has no `tools:` config, `external_mcp_client` is set to `None`. Explicit is better than implicit.

### Q4: LLM prompt injection?

**Decision: A) Yes, auto-inject.** Follow the existing dynamic prompt pattern used by Router (standup report) and Triage (specialist roster). Tool descriptions are appended to the base prompt:

```python
# In GraphBuilder._configure_specialist_adapter()
base_prompt = load_prompt(prompt_file)
tool_descriptions = self._format_tool_descriptions(specialist_config.get("tools", {}))
if tool_descriptions:
    dynamic_prompt = f"{base_prompt}\n\n{tool_descriptions}"
else:
    dynamic_prompt = base_prompt
```

This keeps prompts in sync with actual permissions automatically.

### Q5: Granularity beyond tool names?

**Decision: No.** Tool-level granularity is sufficient for V1. Argument-level restrictions (path allowlists, size limits) are overkill.

### Q6: Config-controlled ReActMixin?

**Decision: Yes.** Specialists can opt into iterative tool use via config:

```yaml
batch_processor_specialist:
  type: "llm"
  tools:
    filesystem:
      - read_file
      - write_file
      - move_file
  react:
    enabled: true
    max_iterations: 5
    stop_on_error: true
```

**Implementation:** GraphBuilder wraps specialist with `ReactEnabledSpecialist` at runtime if `react.enabled: true`. No change to specialist class definitions. ProjectDirector's code-level ReActMixin inheritance is removed.

**Global defaults** can be set at root level:
```yaml
react:
  defaults:
    max_iterations: 10
    stop_on_error: false
```

Precedence: per-specialist > global > hardcoded fallback (10 iterations).

**References:** ADR-BATCH-001 (Content-Based File Operations - deferred ReActMixin, now superseded)

---

## Consequences

### Positive

- **Visibility**: Config shows exactly what tools each specialist has
- **Guardrails**: Runtime enforcement prevents unauthorized tool use
- **Principle of least privilege**: Specialists get only what they need
- **Auditability**: Config diff shows permission changes

### Negative

- **Migration effort**: Need to audit all specialists and add `tools:` config
- **Config verbosity**: More lines in config.yaml
- **Runtime overhead**: Permission check on every MCP call (negligible)

### Neutral

- Changes config schema (additive, non-breaking in Phase 1)
- Requires `PermissionedMcpClient` wrapper class

---

## References

- ADR-CORE-035: Filesystem Architecture Consolidation (external MCP introduction)
- ADR-MCP-003: External MCP Container Integration
- Issue #53: Routing misroutes file read (exposed lack of config-level tool visibility)
- `graph_builder.py:179-182`: Current blanket injection of external_mcp_client
