# ADR-CORE-008: MCP (Message-Centric Protocol) Architecture

**Status:** ACCEPTED
**Date:** 2025-11-07
**Implements:** Roadmap Tasks 2.4-2.6 (Workstream 2: The Explicit Control Plane)
**Related ADRs:** ADR-CORE-003 (Dossier Pattern), ADR-CORE-004 (Dossier State Management)

---

## Context

The system currently relies on two primary communication mechanisms between specialists:

1. **Graph-mediated routing** - Specialists modify GraphState and routing decisions flow through the RouterSpecialist, incurring LLM invocation costs and latency
2. **Dossier pattern** (ADR-CORE-003/004) - Asynchronous, state-mediated handoffs for workflow coordination

However, neither pattern efficiently handles **synchronous, deterministic service calls** where one specialist needs to invoke a simple function on another specialist (e.g., "Does file X exist?", "What's the current date?"). These operations should not require:
- Graph routing decisions
- LLM invocations
- Asynchronous handoffs
- State transitions

The absence of a synchronous invocation mechanism creates several problems:

1. **Latency overhead** - Simple operations require full graph routing cycles
2. **Cost inefficiency** - Deterministic queries trigger expensive LLM calls
3. **Integration barriers** - Cannot easily leverage existing OSS graph-as-a-service projects (Deep Research, Deep Reasoning) that expose service interfaces
4. **Architectural coupling** - Specialists cannot directly consume services from other specialists without tight coupling

This ADR introduces **MCP (Message-Centric Protocol)**, a synchronous service invocation layer that complements the existing Dossier pattern.

---

## Decision

We introduce MCP (Message-Centric Protocol) as a **synchronous, direct service invocation mechanism** between specialists, implementing the following architecture:

### 1. Core Schemas

**McpRequest** (Pydantic model):
```python
class McpRequest(BaseModel):
    service_name: str          # Specialist identifier (e.g., "file_specialist")
    function_name: str         # Function to invoke (e.g., "read_file")
    parameters: Dict[str, Any] # Function arguments as key-value pairs
    request_id: str            # UUID for distributed tracing (auto-generated)
```

**McpResponse** (Pydantic model):
```python
class McpResponse(BaseModel):
    status: Literal["success", "error"]  # Execution status
    data: Optional[Any]                  # Return value (only on success)
    error_message: Optional[str]         # Error details (only on error)
    request_id: Optional[str]            # Echo of request_id for tracing

    def raise_for_error(self):
        """Convenience method to raise ValueError on error status"""
```

### 2. Registry Architecture

**Per-Graph-Instance Registry** (not singleton):
```python
class McpRegistry:
    def __init__(self, config: ConfigLoader):
        self.services: Dict[str, Dict[str, Callable]] = {}
        self.tracing_enabled = config.get('mcp.tracing_enabled', True)
        self.timeout_seconds = config.get('mcp.timeout_seconds', 5)

    def register_service(self, service_name: str, functions: Dict[str, Callable])
    def dispatch(self, request: McpRequest) -> McpResponse
```

**Rationale for per-graph-instance scope:**
- **Test isolation** - Each test creates its own GraphBuilder → own registry
- **Concurrent graphs** - Multiple graph instances can run simultaneously without service conflicts
- **Graph-specific configuration** - Different graphs can have different MCP configurations
- **No global state** - Avoids singleton anti-pattern and hidden dependencies

### 3. Client Interface

**McpClient** (convenience wrapper):
```python
class McpClient:
    def __init__(self, registry: McpRegistry):
        self.registry = registry

    def call(self, service_name: str, function_name: str, **parameters) -> Any:
        """Raises ValueError on error, returns data on success"""

    def call_safe(self, service_name: str, function_name: str, **parameters) -> tuple[bool, Any]:
        """Returns (success, result) tuple, never raises"""
```

**Design rationale:**
- `call()` - Pythonic exception-based error handling for most use cases
- `call_safe()` - Tuple-based error handling for fault-tolerant workflows
- Both methods automatically serialize/deserialize McpRequest/McpResponse

### 4. Graph Lifecycle Integration

**GraphBuilder initialization:**
```python
class GraphBuilder:
    def __init__(self, config: ConfigLoader):
        self.config = config
        self.mcp_registry = McpRegistry(self.config)  # Per-graph-instance
        # ...

    def load_and_configure_specialists(self):
        # After loading all specialists:
        mcp_client = McpClient(self.mcp_registry)

        for instance in loaded_specialists.values():
            instance.mcp_client = mcp_client  # Inject client

            if hasattr(instance, 'register_mcp_services'):
                instance.register_mcp_services(self.mcp_registry)
```

**BaseSpecialist contract:**
```python
class BaseSpecialist(ABC):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        # ...
        self.mcp_client: Optional['McpClient'] = None  # Injected by GraphBuilder

    def register_mcp_services(self, registry: 'McpRegistry'):
        """Optional: Register this specialist's functions as MCP services."""
        pass  # Default no-op - specialists opt-in to MCP
```

### 5. Timeout Protection

MCP calls are protected by a configurable timeout using `signal.alarm()` (Unix only):

```python
def _execute_with_timeout(self, function: Callable, parameters: Dict[str, Any]) -> Any:
    def timeout_handler(signum, frame):
        raise TimeoutError(f"MCP call exceeded {self.timeout_seconds}s timeout")

    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(self.timeout_seconds)
    try:
        result = function(**parameters)
        signal.alarm(0)  # Cancel alarm
        return result
    finally:
        signal.signal(signal.SIGALRM, old_handler)
```

**Configuration** (`config.yaml`):
```yaml
mcp:
  timeout_seconds: 5  # Maximum execution time per MCP call
```

**Limitation:** `signal.alarm()` only works on Unix systems. Windows support would require threading-based timeout implementation.

### 6. LangSmith Tracing Integration

MCP calls can optionally emit LangSmith trace spans for observability:

```python
def _wrap_with_tracing(self, function: Callable, request: McpRequest) -> Callable:
    if not self.tracing_enabled:
        return function

    try:
        from langsmith import traceable

        @traceable(name=f"mcp_call:{request.service_name}.{request.function_name}")
        def traced_function(**parameters):
            return function(**parameters)

        return traced_function
    except ImportError:
        return function  # Graceful degradation
```

**Configuration kill switch** (`config.yaml`):
```yaml
mcp:
  tracing_enabled: true  # Toggle LangSmith trace spans
```

---

## MCP vs Dossier: When to Use Each

### Use MCP When:
- **Synchronous operations** - Immediate result needed (file existence check, date retrieval)
- **Deterministic functions** - No LLM involvement, pure logic
- **Low-latency requirements** - Cannot afford graph routing overhead
- **Service-oriented calls** - Treating specialist as a utility service
- **External service integration** - Wrapping OSS graph-as-a-service projects

**Example use cases:**
- FileSpecialist.file_exists("report.md") → bool
- DateTimeSpecialist.get_current_date() → str
- ValidationSpecialist.validate_schema(data, schema) → bool
- DeepResearchGraph.research(query) → structured_result

### Use Dossier When:
- **Asynchronous handoffs** - Specialist-to-specialist workflow transitions
- **LLM-driven tasks** - Next specialist needs to perform reasoning
- **State-mediated communication** - Requires graph state transition tracking
- **Complex workflows** - Multi-step orchestration with routing logic

**Example use cases:**
- BuilderSpecialist → CriticSpecialist (review workflow)
- TriageArchitect → Facilitator (context engineering handoff)
- ErrorHandler → HumanEscalation (failure recovery)

### Comparison Matrix

| Aspect | MCP | Dossier |
|--------|-----|---------|
| **Invocation** | Synchronous (function call) | Asynchronous (state transition) |
| **Latency** | Low (~ms) | High (full graph cycle) |
| **Routing** | Direct dispatch | Via RouterSpecialist |
| **LLM Cost** | Zero | Router invocation cost |
| **Use Case** | Utility services | Workflow coordination |
| **State Impact** | No state modification | Explicit state handoff |
| **Traceability** | Optional LangSmith spans | Full graph state history |

---

## Implementation: FileSpecialist as MCP-Only Specialist

FileSpecialist serves as the reference implementation of the **MCP-only pattern**, where a specialist operates exclusively via MCP and never participates in graph routing:

### Service Registration
```python
class FileSpecialist(BaseSpecialist):
    def register_mcp_services(self, registry: 'McpRegistry'):
        """Expose all file operations as MCP services."""
        registry.register_service(self.specialist_name, {
            "file_exists": self.file_exists,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_files": self.list_files,
            "create_directory": self.create_directory,
            "create_zip": self.create_zip,
        })

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """No-op for MCP-only mode."""
        logger.warning(f"{self.specialist_name} operates exclusively via MCP")
        return {}
```

### Security: Path Validation
All FileSpecialist operations enforce path validation to prevent directory traversal:

```python
def _validate_path(self, path: str) -> Path:
    """Validates path is within root_dir, prevents directory traversal."""
    target = Path(path)
    if not target.is_absolute():
        target = self.root_dir / target
    target = target.resolve()  # Handles .. and symlinks
    target.relative_to(self.root_dir)  # Raises ValueError if escapes root_dir
    return target
```

This provides defense-in-depth alongside container isolation.

### Usage from Other Specialists
```python
class ReportGeneratorSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # Synchronous file existence check
        if self.mcp_client.call("file_specialist", "file_exists", path="report.md"):
            content = self.mcp_client.call("file_specialist", "read_file", path="report.md")
            # ... process content ...

        # Write output
        self.mcp_client.call("file_specialist", "write_file",
                           path="output.md", content=report_content)

        return {"artifacts": {"report_path": "output.md"}}
```

---

## Consequences

### Positive

1. **Reduced latency** - Synchronous calls eliminate graph routing overhead
2. **Cost reduction** - Deterministic operations no longer trigger LLM invocations
3. **External integration** - Unlocks OSS graph-as-a-service projects (Deep Research, Deep Reasoning)
4. **Clear separation of concerns** - MCP for services, Dossier for workflows
5. **Test isolation** - Per-graph-instance registry prevents cross-test pollution
6. **Observability** - Optional LangSmith tracing with configuration kill switch
7. **Security** - Path validation in FileSpecialist prevents directory traversal attacks

### Negative

1. **Platform limitation** - Timeout mechanism (signal.alarm) only works on Unix systems
2. **Synchronous blocking** - MCP calls block the caller (acceptable for fast operations)
3. **No retry logic** - Failures require caller to implement retry strategies
4. **Limited error propagation** - Errors become ValueError exceptions (simple but lossy)
5. **Configuration complexity** - Adds another communication pattern to learn

### Risks & Mitigations

**Risk:** Developers overuse MCP for tasks better suited to graph routing
**Mitigation:** Clear documentation of MCP vs Dossier use cases, code review guidelines

**Risk:** Timeout too short causes spurious failures
**Mitigation:** Configurable timeout in config.yaml, can be tuned per deployment

**Risk:** Missing LangSmith traces for debugging
**Mitigation:** Tracing enabled by default, only disable if overhead becomes issue

**Risk:** Windows incompatibility due to signal.alarm
**Mitigation:** Document Unix-only limitation, future enhancement for threading-based timeout

---

## Future Enhancements

### Short-term
1. **Async MCP support** - Optional async variants of call() for non-blocking operations
2. **Retry policies** - Configurable retry strategies for transient failures
3. **Circuit breaker integration** - MCP failures should trigger system invariants (Task 1.4-1.6)

### Long-term
1. **Windows timeout support** - Threading-based timeout implementation for cross-platform compatibility
2. **Service discovery** - Registry introspection API for dynamic service discovery
3. **Remote MCP** - Network-based MCP for multi-process/container architectures
4. **Schema validation** - Pydantic models for MCP function parameters

---

## Compliance with Four Pillars

### Pillar 1: Aggressive Resilience
- ✅ Timeout protection prevents hanging calls
- ✅ Clear error responses with status/error_message
- ⚠️ No retry logic (future enhancement)

### Pillar 2: Explicit State as Control Plane
- ✅ MCP provides deterministic, structured communication
- ✅ Complements Dossier for complete communication coverage
- ✅ No implicit LLM inference for service calls

### Pillar 3: Hybrid Routing Engine
- ✅ MCP serves as procedural layer for deterministic service calls
- ✅ Bypasses LLM routing for synchronous operations
- ✅ Integrates into hybrid routing prioritization (future Task 3.5)

### Pillar 4: Professionalized Platform & Tooling
- ✅ LangSmith tracing integration for observability
- ✅ Configuration-driven behavior (timeout, tracing)
- ✅ Per-graph-instance architecture supports concurrent graphs

---

## References

- Roadmap Tasks 2.4-2.6 (Workstream 2: The Explicit Control Plane)
- ADR-CORE-003: Dossier Pattern (Asynchronous Communication)
- ADR-CORE-004: Dossier State Management
- FileSpecialist: Reference implementation (app/src/specialists/file_specialist.py)
- MCP Test Suite: 66 tests (test_mcp_schemas.py, test_mcp_registry.py, test_mcp_client.py)
