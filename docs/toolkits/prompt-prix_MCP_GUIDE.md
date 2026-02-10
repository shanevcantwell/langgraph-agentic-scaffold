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
| `file_specialist` | read_file, write_file, list_dir, delete, rename | Filesystem ops |
| `summarizer_specialist` | summarize | Text condensation |
| `inference_service` | judge_relevance, detect_contradiction | Semantic judgment |
| `fara_service` | locate, verify, screenshot | Visual grounding |

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
| `semantic-chunker` | semantic-chunker-mcp | Embedding tools for semantic analysis (calculate_drift, etc.) |
| `prompt-prix` | prompt-prix-mcp | Model evaluation, ReAct iteration, drift measurement, prompt geometry |

### prompt-prix Tool Surface

| Tool | Purpose |
|------|---------|
| `react_step()` | Single stateless ReAct iteration: trace in, new iterations out |
| `complete()` | Base completion primitive |
| `judge()` | LLM-as-judge (deprecated — prefer semantic-chunker tools for deterministic eval) |
| `list_models()` | Discover available models on configured LM Studio servers |
| `calculate_drift()` | Cosine distance via NV-Embed-v2 embeddings (proxied to semantic-chunker) |
| `analyze_variants()` | Prompt phrasing geometry in 4096-dim embedding space |
| `generate_variants()` | Generate prompt phrasing variants |
| `analyze_trajectory()` | ReAct trajectory quality assessment |
| `compare_trajectories()` | Cross-trajectory comparison |

prompt-prix manages its own LM Studio connections (two servers via `LM_STUDIO_SERVER_1`/`LM_STUDIO_SERVER_2` env vars). Its pool operates independently from LAS's `PooledLMStudioAdapter` — see ADR-068 accepted risk.

Timeout: 600s (covers worst-case 300s queue wait + 300s inference).

See [ADR-CORE-064](../ADRs/proposed/ADR-CORE-064_Prompt-Prix-MCP-Integration.md) for integration architecture.

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
