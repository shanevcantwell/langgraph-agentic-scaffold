# ADR-MCP-003: External MCP Container Integration

**Status**: Accepted
**Date**: 2025-11-22
**Scope**: MCP Architecture, Container Integration, External Services

## Context

The Model Context Protocol (MCP) defines a standard for communication between LLM applications and external services/tools. Our system currently implements **internal MCP** (Python-to-Python synchronous function calls via `McpClient` and `McpRegistry`). However, the broader MCP ecosystem includes powerful **external MCP servers** (Node.js, Go, Python containerized services) that provide specialized capabilities:

- **@modelcontextprotocol/server-filesystem**: Comprehensive file operations with security boundaries
- **Future examples**: Database connectors, API clients, code execution sandboxes, web scrapers

### Current Architecture Gap

**Internal MCP** (`app/src/mcp/`):
- **Protocol**: Direct Python function calls (synchronous)
- **Registration**: `McpRegistry` maps service_name → Python callable
- **Communication**: In-process, no serialization overhead
- **Lifecycle**: Managed within Python process

**External MCP Servers**:
- **Protocol**: JSON-RPC over stdio/HTTP (asynchronous)
- **Registration**: Container lifecycle management (Docker)
- **Communication**: Inter-process via subprocess stdin/stdout
- **Lifecycle**: Long-lived external processes with health checks

**The Gap**: Specialists currently cannot call external MCP containers. This limits access to the broader MCP ecosystem and prevents migration of specialists to external containerized services.

### Strategic Drivers

1. **Ecosystem Access**: Leverage community-built MCP servers (filesystem, databases, APIs)
2. **Specialist Migration**: Reduce internal specialist count by delegating to external containers (per ADR-CORE-013)
3. **Batch Processor Pattern**: Enable `BatchProcessorSpecialist` to orchestrate ANY MCP service (internal or external)
4. **Future-Proofing**: Align with MCP specification and industry best practices

## Decision

Implement **external MCP container integration** using a **dual-client architecture** with **fail-fast error handling** (Stage 1). Future graceful degradation/fallback will be addressed in a separate ADR (Stage 2).

### Architecture: Dual-Client Pattern

```
┌──────────────────────────────────────────────────────────────────┐
│                    Specialist (BaseSpecialist)                   │
│                                                                   │
│  ┌──────────────────────┐         ┌──────────────────────────┐  │
│  │  Internal MCP        │         │  External MCP            │  │
│  │  (McpClient)         │         │  (ExternalMcpClient)     │  │
│  │                      │         │                          │  │
│  │  - Sync Python calls │         │  - Async JSON-RPC        │  │
│  │  - In-process        │         │  - Subprocess mgmt       │  │
│  │  - No serialization  │         │  - Container lifecycle   │  │
│  └──────────┬───────────┘         └──────────┬───────────────┘  │
│             │                                │                   │
│             ▼                                ▼                   │
│  ┌──────────────────────┐         ┌──────────────────────────┐  │
│  │  McpRegistry         │         │  Container Pool          │  │
│  │  (service → func)    │         │  (service → session)     │  │
│  └──────────────────────┘         └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions**:
1. **Separate Clients**: Keep internal MCP (sync) and external MCP (async) as distinct systems
2. **Explicit Service Type**: Specialists explicitly choose internal vs external client
3. **Fail-Fast**: External MCP failures raise exceptions immediately (no fallback in Stage 1)
4. **Long-Lived Connections**: Containers launched at startup, connections persist until shutdown

### Transport: stdio (Subprocess Communication)

**Selected Transport**: **stdio** (JSON-RPC over subprocess stdin/stdout)

**Rationale**:
- **Simplicity**: No network configuration or ports required
- **Docker Compatibility**: `-i` flag maintains stdin connectivity
- **Lifecycle Management**: Container lives only as long as connection exists
- **Security**: Process isolation without network exposure

**Alternative Considered**: Streamable HTTP (server-sent events)
- **Pros**: Multiple clients, independent server process, better for production at scale
- **Cons**: Requires port management, network configuration, session lifecycle complexity
- **Decision**: Defer HTTP transport until production deployment requirements are clearer

### Security Model

**File System Access Control** (Filesystem MCP Server):
1. **Workspace Mounting**: Only mount workspace directory to `/projects` in container
2. **Read-Only Option**: Support `:ro` flag for sandboxed operations
3. **Allowed Directories**: Filesystem server enforces paths specified at startup
4. **No Sensitive Mounts**: Never mount `/app`, `/etc`, or system directories

**Container Execution Control**:
1. **Whitelist Images**: Only allow configured container images (no arbitrary docker run)
2. **Resource Limits**: Configure CPU/memory limits for containers
3. **Security Options**: Use Docker security features (`--cap-drop`, `--security-opt`)

### Container Lifecycle

**Startup Sequence**:
1. Application starts → `GraphBuilder.build()` creates graph
2. `GraphBuilder.initialize_external_mcp()` launches configured containers
3. For each enabled external service:
   - Spawn subprocess via `docker run -i --rm ...`
   - Establish JSON-RPC session via MCP Python SDK
   - Initialize connection (`session.initialize()`)
   - Store session in `ExternalMcpClient.sessions` dict
4. Attach `external_mcp_client` to specialists that need it
5. Application ready (fail-fast if critical external services unavailable)

**Shutdown Sequence**:
1. Application shutdown triggered
2. `ExternalMcpClient.cleanup()` closes all sessions
3. Containers terminate when stdin closes (auto-cleanup via `--rm` flag)

**Health Checks** (Future Enhancement):
- Periodic `list_tools()` calls to verify container responsiveness
- Automatic reconnection with exponential backoff on failure
- Circuit breaker pattern if failure rate exceeds threshold

## Implementation Details

### Core Components

#### 1. ExternalMcpClient (`app/src/mcp/external_client.py`)

```python
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class ExternalMcpClient:
    """
    Client for external MCP containers (Node.js servers, Docker, etc).

    Manages subprocess lifecycle and JSON-RPC protocol communication
    using the official MCP Python SDK. Separate from internal McpClient.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("external_mcp", {})
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tracing_enabled = self.config.get("tracing_enabled", True)

    async def connect_service(self, service_name: str, command: str, args: list[str]):
        """Launch subprocess and establish MCP session"""
        server_params = StdioServerParameters(command=command, args=args, env=None)

        # Launch subprocess and get stdio streams
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = stdio_transport

        # Create and initialize session
        session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await session.initialize()

        # Store session
        self.sessions[service_name] = session
        logger.info(f"Connected to external MCP service '{service_name}'")

    async def call_tool(self, service_name: str, tool_name: str, arguments: dict):
        """Call a tool on an external MCP service (fail-fast on errors)"""
        if service_name not in self.sessions:
            raise ValueError(f"External MCP service '{service_name}' not connected")

        session = self.sessions[service_name]
        result = await session.call_tool(tool_name, arguments=arguments)
        return result

    async def cleanup(self):
        """Close all connections and cleanup resources"""
        await self.exit_stack.aclose()
        self.sessions.clear()
```

#### 2. GraphBuilder Integration

```python
# app/src/workflow/graph_builder.py

class GraphBuilder:
    def __init__(self, config: dict):
        # ... existing code ...
        self.mcp_registry = McpRegistry(config)  # Internal MCP
        self.external_mcp_client = None  # External MCP (lazy init)

    async def initialize_external_mcp(self):
        """Initialize external MCP services at startup"""
        external_config = self.config.get("mcp", {}).get("external_mcp", {})

        if not external_config or not external_config.get("enabled", False):
            logger.info("External MCP not enabled")
            return

        self.external_mcp_client = ExternalMcpClient(self.config)

        # Connect to configured services
        services = external_config.get("services", {})
        for service_name, service_config in services.items():
            if not service_config.get("enabled", False):
                continue

            command = service_config["command"]
            args = service_config["args"]

            try:
                await self.external_mcp_client.connect_service(
                    service_name, command, args
                )
            except Exception as e:
                # Fail-fast if critical service unavailable
                if service_config.get("required", False):
                    raise RuntimeError(
                        f"Critical external MCP service '{service_name}' failed to start: {e}"
                    ) from e
                else:
                    logger.warning(f"Optional external MCP service '{service_name}' unavailable: {e}")
```

#### 3. Configuration Schema (`config.yaml`)

```yaml
mcp:
  # Internal MCP (existing)
  tracing_enabled: true
  timeout_seconds: 5

  # External MCP (new)
  external_mcp:
    enabled: true  # Global enable/disable
    tracing_enabled: true
    services:
      filesystem:
        enabled: true
        required: false  # Fail-fast if true and unavailable
        command: "docker"
        args:
          - "run"
          - "-i"
          - "--rm"
          - "-v"
          - "${WORKSPACE_PATH}:/projects"  # Environment variable substitution
          - "mcp/filesystem"
          - "/projects"
        allowed_directories:
          - "/projects"
```

#### 4. Docker Compose Updates

```yaml
# docker-compose.yml
services:
  langgraph-app:
    # ... existing config ...
    volumes:
      - ./:/app
      - /var/run/docker.sock:/var/run/docker.sock  # NEW: Docker socket access
    environment:
      - WORKSPACE_PATH=/app  # NEW: Workspace path for MCP containers
```

### Async/Sync Bridging Strategy

**Current Reality**: Graph execution is synchronous, but external MCP requires async.

**Stage 1 Solution**: Run async calls in event loop from sync context

```python
import asyncio

def sync_call_external_mcp(external_client, service_name, tool_name, arguments):
    """Bridge sync specialist code to async external MCP"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            external_client.call_tool(service_name, tool_name, arguments)
        )
    finally:
        loop.close()
```

**Long-Term Solution** (ADR-CORE-014): Migrate graph execution to async
- LangGraph supports async node execution
- Would improve concurrency for all operations
- Requires refactoring all specialists and tests

## Stage 1: Fail-Fast Implementation

**Philosophy**: External MCP services are explicit dependencies. If configured and unavailable, fail loudly.

**Error Handling**:
- **Connection failures**: Raise `RuntimeError` during startup
- **Tool call failures**: Raise exceptions immediately, no retry
- **Container crashes**: Propagate error to caller

**Rationale**:
1. **Clarity**: Developers immediately know when external services are down
2. **Simplicity**: No complex fallback logic to maintain
3. **Debugging**: Clear error messages with stack traces
4. **Precedent**: Gemini adapter uses `@retry` for transient errors, but still re-raises after final attempt

**Inspired by Gemini Adapter Pattern** (`app/src/llm/gemini_adapter.py:53-57, 98-120`):
- Specific exception types for different failure modes (`RateLimitError`, `ProxyError`)
- Clear error messages for debugging
- Re-raise after handling to preserve stack traces

## Stage 2: Optional Fallback (Future ADR)

**Deferred to separate ADR** (referenced in ADR-CORE-013):

**Proposed Pattern** (similar to Gemini's `_robustly_parse_json_from_text` fallback):
1. Try external MCP call
2. If connection failed AND internal implementation exists, try internal fallback
3. If both fail, raise clear error with both failure reasons

**Configuration**:
```yaml
services:
  filesystem:
    enabled: true
    required: false  # Allow fallback
    fallback_to_internal: true  # Use file_specialist if container unavailable
```

**Benefits**:
- Graceful degradation when containers unavailable
- Development without Docker dependencies
- Phased rollout (internal → external migration)

**Costs**:
- Increased complexity
- Potential behavioral differences (internal vs external implementations)
- Testing overhead (must test both paths)

**Decision Criteria for Stage 2**:
- User demand for offline/development mode
- Production reliability requirements
- Availability of internal fallback implementations

## Consequences

### Positive

1. **Ecosystem Access**: Can now use community MCP servers (filesystem, databases, APIs)
2. **Specialist Reduction**: Can migrate internal specialists to external containers (file_specialist → filesystem MCP)
3. **Batch Orchestration**: `BatchProcessorSpecialist` can orchestrate ANY MCP service
4. **Separation of Concerns**: Dual-client architecture keeps internal/external MCP cleanly separated
5. **Security**: Container isolation + allowed directory restrictions
6. **Observability**: LangSmith can trace external MCP calls
7. **Industry Alignment**: Follows MCP specification and best practices

### Negative

1. **Async Complexity**: Sync/async bridging adds boilerplate (mitigated by helper functions)
2. **Startup Latency**: Container launches add 1-3 seconds to startup time
3. **Docker Dependency**: Requires Docker installed and Docker socket access
4. **Error Surface**: New failure modes (container crashes, network issues, subprocess errors)
5. **Testing Complexity**: Integration tests require Docker environment

### Mitigations

1. **Async Bridging**: Centralized helper function (`sync_call_external_mcp`)
2. **Startup Latency**: Long-lived connections (launch once at startup, not per-request)
3. **Docker Dependency**: Document requirement clearly, fail-fast with helpful error
4. **Error Surface**: Comprehensive error messages, LangSmith tracing, health checks (future)
5. **Testing**: Mock external MCP client for unit tests, Docker-based integration tests

## Alternatives Considered

### Alternative 1: Unified MCP Client (Single Interface)

Create one `McpClient` that handles both internal and external services transparently.

**Pros**:
- Single interface for specialists
- Transparent service location

**Cons**:
- Mixing async/sync patterns is complex
- Less explicit about where services run
- Harder to maintain and test
- Breaks existing internal MCP API

**Decision**: Rejected. Dual-client pattern is clearer and maintains backward compatibility.

### Alternative 2: HTTP Transport Instead of stdio

Use HTTP/SSE transport for external MCP communication.

**Pros**:
- Better for multiple clients
- Independent server lifecycle
- Production-grade architecture

**Cons**:
- Requires port management
- Network configuration complexity
- Session lifecycle management
- Overkill for single-client use case

**Decision**: Defer HTTP transport until production requirements demand it.

### Alternative 3: Sync Wrapper for External MCP

Wrap async MCP SDK in synchronous API to match internal MCP.

**Pros**:
- Consistent API across internal/external
- No async/sync bridging in specialists

**Cons**:
- Hides async nature (future performance issues)
- Blocks event loop (bad practice)
- Prevents future async migration

**Decision**: Rejected. Better to be explicit about async and plan for async migration (ADR-CORE-014).

## Related Work

- **ADR-CORE-008**: MCP Architecture ✅ IMPLEMENTED (internal Python MCP)
- **ADR-CORE-013**: Specialist Organization Strategy (motivation for external MCP migration)
- **ADR-CORE-014**: Async Graph Execution Migration (long-term async solution)
- **ADR-MCP-001**: File Service Permissions Split (security concern for file operations)
- **ADR-MCP-002**: The Dockyard Architecture (uploaded file handling)

## Implementation Checklist

- [ ] Create `ExternalMcpClient` class (`app/src/mcp/external_client.py`)
- [ ] Add `mcp` package dependency (`pyproject.toml`)
- [ ] Update `GraphBuilder` with async initialization (`app/src/workflow/graph_builder.py`)
- [ ] Add Docker socket access (`docker-compose.yml`)
- [ ] Add external MCP configuration (`config.yaml`)
- [ ] Create integration test (`app/tests/integration/test_external_mcp.py`)
- [ ] Update MCP documentation (`docs/MCP_GUIDE.md`)
- [ ] Test with filesystem MCP container
- [ ] Verify LangSmith tracing captures external MCP calls
- [ ] Document troubleshooting guide for container issues

## References

- MCP Specification: https://modelcontextprotocol.io/
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Filesystem MCP Server: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
- Gemini Adapter Fallback Pattern: `app/src/llm/gemini_adapter.py:53-120, 173-182`

## Open Questions

1. **Health Check Frequency**: How often should we ping external containers? (Future enhancement)
2. **Reconnection Strategy**: Exponential backoff? Max retries? (Future enhancement)
3. **Resource Limits**: Should we configure CPU/memory limits for containers? (Future enhancement)
4. **Multi-Container Orchestration**: How to handle dependencies between external MCP services? (Future consideration)

---

**Status**: Ready for implementation
**Next Step**: Implement `ExternalMcpClient` and integration test
