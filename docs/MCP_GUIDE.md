# MCP in LAS

MCP (Model Context Protocol) provides synchronous service calls between components. LAS uses MCP for two purposes:

1. **Internal services** - Python functions callable by other specialists
2. **External containers** - Dockerized MCP servers integrated at runtime

---

## 1. Internal MCP

### Calling a Service

```python
# From any specialist with mcp_client injected
result = self.mcp_client.call("file_specialist", "read_file", path="/workspace/data.txt")

# Fault-tolerant version (returns tuple)
success, result = self.mcp_client.call_safe("file_specialist", "read_file", path="/workspace/data.txt")
```

### Registering a Service

```python
class MySpecialist(BaseSpecialist):
    def register_mcp_services(self, registry: McpRegistry):
        registry.register_service(self.specialist_name, {
            "my_function": self.my_function,
        })

    def my_function(self, param: str) -> dict:
        return {"result": param.upper()}
```

### Current Internal Services

| Service | Functions | Purpose |
|---------|-----------|---------|
| `systems_architect` | create_plan | Planning service — produces SystemPlan for any specialist (#115) |
| `summarizer_specialist` | summarize | Text condensation |

> **Note:** Many former internal MCP services (file_specialist, inference_service, fara_service) have been replaced by external MCP containers or absorbed by specialists.

---

## 2. External MCP (Containers)

External MCP servers run as Docker containers, communicating via stdio JSON-RPC.

### Configuration

```yaml
# config.yaml
mcp:
  external_mcp:
    enabled: true
    services:
      navigator:
        enabled: true
        command: "docker"
        args: ["run", "-i", "--rm", "--network", "host", "surf-mcp"]
```

### Calling External Services

```python
from app.src.mcp import sync_call_external_mcp

result = sync_call_external_mcp(
    self.external_mcp_client,
    "navigator",           # service name
    "goto",                # method
    {"url": "https://..."}  # params
)
```

### Container Lifecycle

```python
# Startup (in GraphBuilder or runner.py)
external_client = ExternalMcpClient(config)
await external_client.connect_all()

# Shutdown
await external_client.disconnect_all()
```

### Current External Services

| Service | Container | Purpose |
|---------|-----------|---------|
| `navigator` | surf-mcp | Browser automation with Fara visual grounding |
| `filesystem` | @modelcontextprotocol/server-filesystem | File operations (directory_tree, read_file, etc.) |
| `terminal` | terminal-mcp | Sandboxed shell commands (allowlist-based) |
| `semantic-chunker` | semantic-chunker-mcp | Embedding analysis — embeddinggemma-300m (768-d), NV-Embed-v2 (4096-d) |
| `it-tools-mcp` | wrenchpilot/it-tools-mcp:v5.10.2 | 119 IT utility tools (format_json, convert_json_to_csv, etc.) |
| `prompt-prix` | prompt-prix-mcp | Eval primitives — `react_step`, `complete`, `list_models` (9 tools via FastMCP) |

### react_step MCP Pattern

All ReAct-capable specialists (ProjectDirector, TextAnalysisSpecialist, ExitInterview) use the `react_step` tool from prompt-prix MCP for iterative tool use. The shared helper in `app/src/mcp/react_step.py` provides `call_react_step()` + `build_tool_schemas()` + `dispatch_external_tool()`. Any specialist becomes ReAct-capable by defining a tool routing table and looping on `call_react_step()`.

This replaced the former ~1700-line ReActMixin / ReactEnabledSpecialist / react_wrapper.py codebase.

### fork() — Recursive LAS Invocation

`dispatch_fork()` in `app/src/mcp/fork.py` spawns a child LAS invocation via `graph.invoke()` (in-process, not HTTP). The child runs full LAS (SA → Triage → Facilitator → Router → Specialist → EI), with only Archiver disk write suppressed. Returns the child's full final state dict. Used by ProjectDirector for context-isolated subtasks.

Key features: depth-limited recursion (default max 3), parent-child cascade cancellation via `CancellationManager`, full error context (no string compression).

---

## 3. When to Use MCP

**Use MCP for:**
- Synchronous, deterministic operations
- Service calls that don't need LLM reasoning
- Cross-specialist utility functions

**Don't use MCP for:**
- LLM-driven workflow handoffs (use Dossier pattern)
- Async operations (MCP is sync)
- State management (use GraphState)

---

## 4. Adding a New External Service

```bash
# Use the automation script
python scripts/add_mcp_service.py --service filesystem

# Or manually:
# 1. Add to config.yaml mcp.external_mcp.services
# 2. Ensure Docker image exists
# 3. Restart application
```

See [dev/MCP_AUTOMATION.md](dev/MCP_AUTOMATION.md) for automation details.

---

## 5. Troubleshooting

**Service not found:**
```python
# Check registered services
services = self.mcp_client.list_services()
```

**External container not connecting:**
```bash
# Verify container runs standalone
docker run -i --rm surf-mcp
# Then send JSON-RPC via stdin
```

**Timeout errors:**
```yaml
# config.yaml - increase timeout
mcp:
  timeout_seconds: 10
```

---

## References

- [MCP Specification](https://modelcontextprotocol.io/)
- [Official MCP Servers](https://github.com/modelcontextprotocol/servers)
- [ADR-MCP-003](ADRs/completed/ADR-MCP-003-External-MCP-Container-Integration.md)
