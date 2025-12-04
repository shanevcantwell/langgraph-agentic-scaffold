# Message-Centric Protocol (MCP) Guide

## 1.0 Overview

**Context:** The system provides two primary communication mechanisms between specialists:

1. **Graph-mediated routing** - Specialists modify GraphState and routing flows through the RouterSpecialist
2. **Dossier pattern** - Asynchronous, state-mediated workflow handoffs (see ADR-CORE-003/004)

However, neither pattern efficiently handles **synchronous, deterministic service calls** where one specialist needs to invoke a simple function on another specialist (e.g., "Does file X exist?", "What's the current date?").

**MCP (Message-Centric Protocol)** provides synchronous, direct service invocation between specialists, complementing the existing communication patterns.

## 2.0 MCP Architecture

**Per-Graph-Instance Registry:**
Each `GraphBuilder` creates its own `McpRegistry` instance, ensuring test isolation and supporting concurrent graph execution. Specialists register their service functions during graph initialization.

**Service Registration:**
```python
class MySpecialist(BaseSpecialist):
    def register_mcp_services(self, registry: 'McpRegistry'):
        """Optional: Register this specialist's functions as MCP services."""
        registry.register_service(self.specialist_name, {
            "my_function": self.my_function,
            "another_function": self.another_function,
        })

    def my_function(self, param1: str, param2: int) -> dict:
        """Service function callable via MCP."""
        # ... implementation ...
        return {"result": "data"}
```

**Service Invocation:**
```python
class ConsumerSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # Synchronous call with automatic error handling
        result = self.mcp_client.call("my_specialist", "my_function",
                                      param1="value", param2=42)

        # Fault-tolerant call returning (success, result) tuple
        success, result = self.mcp_client.call_safe("my_specialist", "my_function",
                                                     param1="value", param2=42)
        if success:
            # ... use result ...
        else:
            # ... handle error (result contains error message) ...
```

## 3.0 When to Use MCP vs Dossier

**Use MCP When:**
- **Synchronous operations** - Immediate result needed (file existence check, date retrieval)
- **Deterministic functions** - No LLM involvement, pure logic
- **Low-latency requirements** - Cannot afford graph routing overhead
- **Service-oriented calls** - Treating specialist as a utility service

**Examples:**
- `self.mcp_client.call("file_specialist", "file_exists", path="report.md")` → bool
- `self.mcp_client.call("datetime_specialist", "get_current_date")` → str
- `self.mcp_client.call("validation_specialist", "validate_schema", data=..., schema=...)` → bool

**Use Dossier When:**
- **Asynchronous handoffs** - Specialist-to-specialist workflow transitions
- **LLM-driven tasks** - Next specialist needs to perform reasoning
- **State-mediated communication** - Requires graph state transition tracking
- **Complex workflows** - Multi-step orchestration with routing logic

**Examples:**
- BuilderSpecialist → CriticSpecialist (review workflow)
- TriageArchitect → Facilitator (context engineering handoff)
- ErrorHandler → HumanEscalation (failure recovery)

## 4.0 MCP Configuration

MCP behavior is controlled via `config.yaml`:

```yaml
mcp:
  # Toggle LangSmith trace spans for MCP calls
  tracing_enabled: true

  # Maximum execution time per MCP call (prevents hanging)
  timeout_seconds: 5
```

**Timeout Protection:** MCP calls are protected by a configurable timeout (default: 5 seconds) using `signal.alarm()`. Note: This mechanism is Unix-only; Windows support requires threading-based implementation.

**LangSmith Tracing:** When enabled, MCP calls emit trace spans for observability. Gracefully degrades if LangSmith is not installed.

## 5.0 Reference Implementation: FileSpecialist

The `FileSpecialist` demonstrates the **MCP-only pattern**, where a specialist operates exclusively via MCP and never participates in graph routing:

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

**Security Note:** FileSpecialist implements path validation using `pathlib.Path.resolve()` and `relative_to()` to prevent directory traversal attacks, providing defense-in-depth alongside container isolation.

**Additional Documentation:** See `ADR-CORE-008_MCP-Architecture.md` for complete architectural details and design decisions.

## 5.1 User Interface Layer Pattern: FileOperationsSpecialist

**Problem:** MCP-only specialists cannot be routed to directly by users. How do users trigger file operations?

**Solution:** Separate the **interface layer** (routable, LLM-driven) from the **service layer** (MCP-only, procedural).

```python
class FileOperationsSpecialist(BaseSpecialist):
    """
    User interface layer for file operations.

    Interprets user requests and routes to FileSpecialist via MCP.
    This specialist IS routable - it serves as the user-facing interface.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Use LLM to parse user intent
        request = StandardizedLLMRequest(
            messages=state["messages"],
            tools=[FileOperation],  # Pydantic schema for operations
            force_tool_call=True
        )

        response = self.llm_adapter.invoke(request)
        operation = response["tool_calls"][0]['args']['operation']

        # Route to FileSpecialist via MCP
        if operation == "list_files":
            files = self.mcp_client.call("file_specialist", "list_files", path=".")
            return {"messages": [AIMessage(content=f"Files: {files}")]}
        # ... other operations
```

**Architecture Pattern (aligns with ADR-MCP-002 Dockyard):**

```
┌─────────────────────────┐
│ User: "list files"      │
└───────────┬─────────────┘
            ↓
┌──────────────────────────────────┐
│ Router (sees only interface      │
│ layer specialists)               │
└───────────┬──────────────────────┘
            ↓
┌──────────────────────────────────┐
│ FileOperationsSpecialist         │
│ (Interface Layer - Routable)     │
│ - LLM-driven intent parsing      │
│ - Formats user-friendly responses│
└───────────┬──────────────────────┘
            ↓ MCP Call
┌──────────────────────────────────┐
│ FileSpecialist                   │
│ (Service Layer - MCP-only)       │
│ - Procedural file operations     │
│ - Path validation & security     │
└──────────────────────────────────┘
```

**Benefits:**
- ✅ **Separation of Concerns:** Interface logic (parsing, formatting) separate from service logic (file I/O)
- ✅ **Architectural Purity:** FileSpecialist remains MCP-only as designed
- ✅ **Extensibility:** FileOperationsSpecialist can route to multiple MCP services (future: DockmasterSpecialist)
- ✅ **Testability:** Both layers can be tested independently

**When to Use This Pattern:**
- MCP service needs to be accessed by users directly (not just other specialists)
- Need LLM-driven intent parsing for natural language requests
- Want to maintain clean separation between interface and service layers

## 5.2 Advanced Pattern: Internal Iteration with MCP (BatchProcessorSpecialist)

**Problem:** How do you process collections of items (e.g., sorting multiple files) without creating graph-level loops?

**Solution:** Use **internal iteration** within a single specialist, calling MCP services for each item. The graph sees a single atomic operation, but internally the specialist iterates over the collection.

```python
class BatchProcessorSpecialist(BaseSpecialist):
    """
    Processes collections of files with emergent LLM-driven sorting logic.

    Architecture: Single graph node with internal iteration.
    From graph perspective: Router → BatchProcessor → Router (atomic)
    Internal perspective: Loops over files, calls MCP for each
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Phase 1: LLM parses user request into structured batch
        batch_request = self._parse_batch_request(state["messages"])
        # Result: ["e.txt", "l.txt", "n.txt"] + ["a-m/", "n-z/"]

        # Phase 2: LLM generates sorting plan (emergent logic)
        sort_plan = self._generate_sort_plan(batch_request)
        # Result: [
        #   {file: "e.txt", dest: "a-m/", rationale: "starts with e"},
        #   {file: "l.txt", dest: "a-m/", rationale: "starts with l"},
        #   ...
        # ]

        # Phase 3: Execute moves via MCP (internal iteration)
        results = {"successful": [], "failed": []}

        for decision in sort_plan.decisions:
            try:
                # Check file exists
                exists = self.mcp_client.call(
                    "file_specialist", "file_exists", path=decision.file_path
                )

                if not exists:
                    results["failed"].append({...})
                    continue

                # Create destination directory
                self.mcp_client.call(
                    "file_specialist", "create_directory", path=decision.destination
                )

                # Move file
                new_path = f"{decision.destination}/{Path(decision.file_path).name}"
                self.mcp_client.call(
                    "file_specialist", "rename_file",
                    old_path=decision.file_path, new_path=new_path
                )

                results["successful"].append({...})

            except Exception as e:
                results["failed"].append({"file": decision.file_path, "error": str(e)})

        # Phase 4: Return comprehensive results
        return {
            "artifacts": {
                "batch_sort_summary": {
                    "total": len(sort_plan.decisions),
                    "successful": len(results["successful"]),
                    "failed": len(results["failed"])
                },
                "batch_sort_details": results["successful"] + results["failed"],
                "batch_sort_report.md": self._generate_report(results)
            },
            "messages": [AIMessage(content=self._format_summary(results))],
            "task_is_complete": True
        }
```

**Key Architectural Benefits:**

1. **Atomic Execution** - Graph sees single node, no routing overhead
2. **Emergent Logic** - LLM decides destinations (not hardcoded rules)
3. **Per-Item Error Handling** - Continues processing on failures, tracks each individually
4. **Rich Observability** - Detailed artifacts show decision rationale for each item
5. **No Graph Looping** - Avoids `recommended_next_specialist` complexity

**Graph Flow:**
```
User: "Sort e.txt, l.txt, n.txt, q.txt into a-m/ and n-z/"
  ↓
Router routes to: batch_processor_specialist
  ↓
BatchProcessor (single node execution):
  - Parse request
  - Generate LLM sorting plan
  - Loop internally: for each file, call MCP 4x (exists, create_dir, rename)
  - Return consolidated results
  ↓
Router sees: task_is_complete = True, routes to END
```

**Contrast with Graph-Level Looping:**
```
# Graph-level looping (complex, inefficient):
Router → FileProcessor (file 1) → Router → FileProcessor (file 2) → Router → ...
# 8 routing cycles for 4 files

# Internal iteration (simple, efficient):
Router → BatchProcessor (processes all 4 files) → Router
# 2 routing cycles total
```

**When to Use This Pattern:**
- Processing collections of items (files, records, tasks)
- Need emergent decision-making per item (LLM-driven logic)
- Want atomic operations (all or partial success, no half-finished state)
- Avoiding graph-level looping complexity

## 6.0 Available MCP Services (Service Directory)

The following table documents all MCP services currently available in the system. Use this as a reference when implementing specialists that need to call MCP services.

| Service Name | Function | Parameters | Returns | Description |
|--------------|----------|------------|---------|-------------|
| `file_specialist` | `file_exists` | `path: str` | `bool` | Check if file/directory exists at path |
| `file_specialist` | `read_file` | `path: str` | `str` | Read and return file contents as string |
| `file_specialist` | `write_file` | `path: str, content: str` | `str` | Write content to file, return confirmation message |
| `file_specialist` | `list_files` | `path: str = "."` | `List[str]` | List all files and directories at path |
| `file_specialist` | `create_directory` | `path: str` | `str` | Create directory (and parents if needed) |
| `file_specialist` | `create_zip` | `source_path: str, destination_path: str` | `str` | Create zip archive from source directory |

**Service Discovery at Runtime:**

```python
# Get list of all available services and their functions
services = self.mcp_client.list_services()
# Returns: {'file_specialist': ['file_exists', 'read_file', ...], ...}
```

## 7.0 Integration Examples: Using MCP from Specialists

**Example 1: Check File Existence Before Processing**

```python
class ReportAnalyzerSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        if not self.mcp_client:
            return {"error": "MCP client not available"}

        # Check if previous report exists
        report_exists = self.mcp_client.call(
            "file_specialist",
            "file_exists",
            path="/workspace/previous_report.md"
        )

        if report_exists:
            # Read existing report for context
            old_report = self.mcp_client.call(
                "file_specialist",
                "read_file",
                path="/workspace/previous_report.md"
            )
            logger.info("Found existing report, augmenting analysis")
            # ... process with context ...
        else:
            logger.info("No previous report found, creating new analysis")

        return {"artifacts": {"analysis_complete": True}}
```

**Example 2: Safe Error Handling with `call_safe()`**

```python
class DataProcessorSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # Use call_safe() for graceful error handling
        success, result = self.mcp_client.call_safe(
            "file_specialist",
            "read_file",
            path="/workspace/data.json"
        )

        if not success:
            # result contains error message
            logger.warning(f"Could not read data file: {result}")
            return {
                "messages": [AIMessage(content=f"Unable to access data file: {result}")]
            }

        # result contains file content
        data = json.loads(result)
        # ... process data ...
        return {"artifacts": {"processed_data": data}}
```

**Example 3: Multi-Step Workflow with File Operations**

```python
class WebBuilderSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # 1. List existing files to check workspace state
        files = self.mcp_client.call(
            "file_specialist",
            "list_files",
            path="/workspace/output"
        )
        logger.info(f"Found {len(files)} existing files")

        # 2. Generate HTML content
        html_content = self._generate_html(state)

        # 3. Write HTML to file
        self.mcp_client.call(
            "file_specialist",
            "write_file",
            path="/workspace/output/index.html",
            content=html_content
        )

        # 4. Create archive for download
        archive_path = self.mcp_client.call(
            "file_specialist",
            "create_zip",
            source_path="/workspace/output",
            destination_path="/workspace/website.zip"
        )

        return {
            "artifacts": {
                "html_file": "/workspace/output/index.html",
                "archive": archive_path
            }
        }
```

**Example 4: Conditional MCP Availability**

```python
class FlexibleSpecialist(BaseSpecialist):
    def _execute_logic(self, state: dict) -> dict:
        # Check if MCP client is available (not all graphs may have it)
        if self.mcp_client:
            # Use MCP for file operations
            content = self.mcp_client.call(
                "file_specialist",
                "read_file",
                path="/workspace/config.yaml"
            )
        else:
            # Fallback to alternative approach
            content = state.get("artifacts", {}).get("config_content")

        # ... process content ...
        return {"artifacts": {"processed": True}}
```

## 8.0 Troubleshooting MCP Calls

**Common Errors and Solutions:**

**1. `McpServiceNotFoundError: Service 'my_specialist' not found`**
- **Cause:** Service was not registered or specialist name is misspelled
- **Solution:**
  - Verify specialist implements `register_mcp_services()` method
  - Check `GraphBuilder` logs for service registration messages
  - Use `self.mcp_client.list_services()` to see available services
  - Ensure specialist is loaded (check `config.yaml` and startup logs)

**2. `McpFunctionNotFoundError: Function 'my_func' not found in service 'file_specialist'`**
- **Cause:** Function name typo or function not exposed in service registry
- **Solution:**
  - Check service directory table (Section 6.0) for correct function names
  - Verify function is included in `register_service()` dictionary
  - Function names are case-sensitive

**3. `TimeoutError: MCP call exceeded timeout`**
- **Cause:** Operation took longer than configured timeout (default: 5 seconds)
- **Solution:**
  - Increase timeout in `config.yaml`: `mcp.timeout_seconds: 10`
  - Investigate why operation is slow (large file, complex computation)
  - Consider async alternatives for long-running operations
  - **Note:** Timeout protection uses Unix-only `signal.alarm()` - Windows support pending

**4. `SpecialistError: Path '/../../etc/passwd' escapes root directory`**
- **Cause:** Path validation detected potential directory traversal attack
- **Solution:**
  - Ensure paths are relative to workspace root or absolute within workspace
  - Use forward slashes `/` (not backslashes `\`) in paths
  - Verify path construction logic doesn't include `..` sequences
  - FileSpecialist enforces security boundary at `/workspace`

**5. `ValueError: MCP call failed: <error message>`**
- **Cause:** MCP call returned error status (from `call()` method)
- **Solution:**
  - Read error message for specific failure reason
  - Use `call_safe()` instead of `call()` for inline error handling
  - Check LangSmith traces for detailed error context
  - Verify parameters match function signature

**6. `AttributeError: 'NoneType' object has no attribute 'call'`**
- **Cause:** `self.mcp_client` is `None` (not attached to specialist)
- **Solution:**
  - Verify `GraphBuilder` is attaching MCP client (should happen automatically)
  - Check for test environment - may need to mock `mcp_client`
  - Add defensive check: `if self.mcp_client:` before calling

**Debugging Strategies:**

**1. Enable LangSmith Tracing for MCP Calls**
```yaml
# config.yaml
mcp:
  tracing_enabled: true  # Creates trace spans for each MCP call
```
- View MCP calls as separate spans in LangSmith trace hierarchy
- Inspect request parameters and response data
- Measure latency per MCP call

**2. Check Service Registration Logs**
```bash
# Look for these log messages at startup
grep "Registered MCP services" logs/app.log
grep "McpRegistry" logs/app.log
```
Expected output:
```
INFO: Registered MCP services for 'file_specialist'
DEBUG: McpRegistry: Registered service 'file_specialist' with 6 functions
```

**3. Use Service Discovery to Verify Availability**
```python
# In specialist's _execute_logic() or test
available_services = self.mcp_client.list_services()
logger.info(f"Available MCP services: {available_services}")
```

**4. Inspect Request IDs for Distributed Tracing**
- Each MCP request gets a unique `request_id` (UUID)
- Search logs for `request_id` to trace call through registry → dispatch → function → response
- Format: `McpClient.call: file_specialist.read_file() [request_id=a1b2c3d4...]`

**5. Test MCP Calls in Isolation**
```python
# In pytest
def test_mcp_file_exists(initialized_specialist_factory):
    specialist = initialized_specialist_factory("MySpecialist")

    # Mock the MCP client
    specialist.mcp_client = MagicMock()
    specialist.mcp_client.call.return_value = True

    result = specialist._execute_logic({})

    # Verify MCP call was made correctly
    specialist.mcp_client.call.assert_called_once_with(
        "file_specialist", "file_exists", path="/workspace/test.txt"
    )
```

**Performance Considerations:**

- **MCP Call Latency:** Typically <10ms for simple operations (file_exists)
- **File I/O:** May take 50-200ms for large files (read_file, write_file)
- **Network Calls:** If MCP services are remote (future), expect 100-500ms
- **Timeout Protection:** Default 5s prevents hanging, tune per use case

**Best Practices:**

1. **Always use `call_safe()` for non-critical operations** - Graceful degradation
2. **Check `self.mcp_client` existence before use** - Not available in all contexts
3. **Log MCP errors with context** - Include file paths, specialist name, operation
4. **Use meaningful parameter names** - Improves trace readability
5. **Prefer MCP over graph routing for synchronous ops** - Lower latency, no LLM cost

---

## 9.0 External MCP Containers (ADR-MCP-003)

External MCP enables integration with containerized MCP servers (Node.js, Go, Python) running in Docker. This unlocks the broader MCP ecosystem including community-built servers for filesystems, databases, APIs, and more.

### Architecture: Dual-Client Pattern

```
┌──────────────────────────────────────────────────────────┐
│                 Specialist (BaseSpecialist)              │
│                                                          │
│  ┌──────────────────┐         ┌──────────────────────┐  │
│  │  Internal MCP    │         │  External MCP        │  │
│  │  (McpClient)     │         │  (ExternalMcpClient) │  │
│  │                  │         │                      │  │
│  │  - Sync Python   │         │  - Async JSON-RPC    │  │
│  │  - In-process    │         │  - Subprocesses      │  │
│  │  - No overhead   │         │  - Containers        │  │
│  └────────┬─────────┘         └─────────┬────────────┘  │
│           │                             │                │
│           ▼                             ▼                │
│  ┌──────────────────┐         ┌──────────────────────┐  │
│  │  McpRegistry     │         │  Container Pool      │  │
│  │  (service→func)  │         │  (service→session)   │  │
│  └──────────────────┘         └──────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Key Differences:**
- **Internal MCP**: Python function calls (fast, in-process)
- **External MCP**: JSON-RPC over stdio (async, containerized)
- **Both**: Available to all specialists, explicitly chosen per call

### 9.1 Configuration

> **Note**: The `mcp/filesystem` container example below is for illustration only.
> File operations use the internal `FileSpecialist` MCP service by default (faster, no container overhead).
> Use external MCP for services that require containerization (isolation, different runtimes, etc.).

**Enable in `config.yaml`:**

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
      # Example: Filesystem MCP server (Node.js container)
      # NOTE: Currently disabled - using internal FileSpecialist instead
      filesystem:
        enabled: true
        required: false  # Fail-fast if true and container unavailable
        command: "docker"
        args:
          - "run"
          - "-i"           # REQUIRED: Interactive mode for stdin
          - "--rm"         # Auto-remove container when stopped
          - "-v"
          - "${WORKSPACE_PATH}:/projects"  # Mount workspace
          - "mcp/filesystem"               # Container image
          - "/projects"                    # Allowed directory
```

**Container Setup:**

The official MCP filesystem server is available at:
https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem

Build the container:
```bash
# Clone the MCP servers repository
git clone https://github.com/modelcontextprotocol/servers.git
cd servers

# Build filesystem server Docker image
docker build -t mcp/filesystem -f src/filesystem/Dockerfile .
```

### 9.2 Initialization

External MCP containers are initialized at application startup:

```python
# In application startup (e.g., runner.py, api.py)
async def startup():
    # 1. Build graph
    graph_builder = GraphBuilder(config)
    graph = graph_builder.build()

    # 2. Initialize external MCP (async)
    await graph_builder.initialize_external_mcp()

    # 3. Graph is now ready with both internal and external MCP
    return graph

# At shutdown
async def shutdown(graph_builder):
    await graph_builder.cleanup_external_mcp()
```

**Startup Logs:**
```
INFO: Initializing external MCP services...
INFO: Connecting to external MCP service 'filesystem'...
DEBUG: Command: docker run -i --rm -v /app:/projects mcp/filesystem /projects
INFO: ✓ External MCP service 'filesystem' connected successfully (7 tools available)
INFO: External MCP initialization complete. Connected services: ['filesystem']
```

### 9.3 Using External MCP in Specialists

**From Sync Code (Current Specialists):**

```python
from ..mcp import sync_call_external_mcp

class MySpecialist(BaseSpecialist):
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Check if external MCP client is available
        if not self.external_mcp_client:
            logger.warning("External MCP not available, using fallback")
            return self._fallback_logic(state)

        # Call external MCP filesystem server
        try:
            files = sync_call_external_mcp(
                self.external_mcp_client,
                "filesystem",
                "list_directory",
                {"path": "/projects"}
            )

            content = sync_call_external_mcp(
                self.external_mcp_client,
                "filesystem",
                "read_file",
                {"path": "/projects/data.txt"}
            )

            return {
                "artifacts": {
                    "files": files,
                    "content": content
                }
            }

        except Exception as e:
            logger.error(f"External MCP call failed: {e}")
            return {"error": str(e)}
```

**From Async Code (Future):**

```python
class MyAsyncSpecialist(BaseSpecialist):
    async def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Direct async call (no bridging needed)
        files = await self.external_mcp_client.call_tool(
            "filesystem",
            "list_directory",
            {"path": "/projects"}
        )

        return {"artifacts": {"files": files}}
```

### 9.4 Available External MCP Servers

**Filesystem Server** (Official):
- **Image**: `mcp/filesystem`
- **Tools**: read_file, write_file, list_directory, create_directory, move_file, search_files, get_file_info
- **Use Case**: File operations with security boundaries
- **Repo**: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem

**Community Servers** (Examples from MCP Toolkit):
- **PostgreSQL**: Database queries with read-only access
- **Slack**: Interact with Slack workspaces
- **Puppeteer**: Browser automation and web scraping
- **DuckDuckGo**: Web search capabilities
- **Memory**: Knowledge graph-based persistent memory
- **YouTube Transcripts**: Retrieve transcripts for videos

**Building Custom Servers:**
- Use official MCP SDK (Node.js, Python, Go)
- Follow stdio transport protocol
- Expose tools via JSON-RPC
- See: https://modelcontextprotocol.io/docs/develop/build-server

### 9.5 BatchProcessor + External MCP

The `BatchProcessorSpecialist` can orchestrate external MCP operations with internal iteration:

```python
class BatchProcessorSpecialist(BaseSpecialist):
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Phase 1: LLM determines which files to process
        batch_plan = self._generate_batch_plan(state)

        # Phase 2: Execute via external MCP (internal iteration)
        results = {"successful": [], "failed": []}

        for file_path in batch_plan.file_paths:
            try:
                # Call external filesystem MCP
                content = sync_call_external_mcp(
                    self.external_mcp_client,
                    "filesystem",
                    "read_file",
                    {"path": file_path}
                )

                # Process content
                processed = self._process_content(content)

                # Write back via external MCP
                sync_call_external_mcp(
                    self.external_mcp_client,
                    "filesystem",
                    "write_file",
                    {"path": f"/projects/output/{file_path}", "content": processed}
                )

                results["successful"].append(file_path)

            except Exception as e:
                results["failed"].append({"file": file_path, "error": str(e)})

        # Phase 3: Return consolidated results
        return {
            "artifacts": {
                "batch_summary": results,
                "total": len(batch_plan.file_paths),
                "successful": len(results["successful"])
            },
            "task_is_complete": True
        }
```

**Benefits:**
- **Emergent logic**: LLM decides which files and destinations
- **Atomic execution**: Single graph node processes entire batch
- **External operations**: Leverages containerized MCP tools
- **Error resilience**: Continues processing on individual failures

### 9.6 Troubleshooting External MCP

**Common Errors:**

**1. `ImportError: MCP Python SDK not installed`**
- **Cause**: `mcp` package not in dependencies
- **Solution**: `pip install mcp` or run `bash scripts/sync-reqs.sh`

**2. `RuntimeError: External MCP service 'filesystem' connection failed`**
- **Cause**: Docker container failed to start
- **Solutions**:
  - Verify Docker is running: `docker ps`
  - Check image exists: `docker images | grep mcp/filesystem`
  - Build image if missing (see Section 9.1)
  - Check volume mount path: ensure `WORKSPACE_PATH` is valid
  - Review container logs: `docker logs <container_id>`

**3. `RuntimeError: External MCP tool call failed`**
- **Cause**: Container crashed or tool doesn't exist
- **Solutions**:
  - List available tools: `await external_mcp_client.list_tools("filesystem")`
  - Check container health: `await external_mcp_client.health_check("filesystem")`
  - Review container stderr in application logs

**4. `ValueError: External MCP service 'filesystem' not connected`**
- **Cause**: Service not initialized or initialization failed
- **Solutions**:
  - Check startup logs for initialization errors
  - Verify `enabled: true` in config.yaml
  - Ensure `await graph_builder.initialize_external_mcp()` was called

**Debugging Strategies:**

**1. Enable Debug Logging:**
```yaml
# config.yaml
mcp:
  external_mcp:
    tracing_enabled: true  # LangSmith traces
```

**2. Check Connected Services:**
```python
# In specialist or test
if self.external_mcp_client:
    services = self.external_mcp_client.get_connected_services()
    logger.info(f"Connected external MCP services: {services}")
```

**3. Test Container Manually:**
```bash
# Test filesystem container outside application
docker run -i --rm -v $(pwd):/projects mcp/filesystem /projects
# Then send JSON-RPC messages via stdin
```

**4. Health Check:**
```python
# Verify service is alive
is_alive = await external_mcp_client.health_check("filesystem")
if not is_alive:
    logger.error("Filesystem service not responding")
```

### 9.7 Security Considerations

**Container Isolation:**
- Only mount necessary directories (workspace, not root)
- Use read-only mounts where possible: `-v ${WORKSPACE_PATH}:/projects:ro`
- Leverage filesystem server's `allowed_directories` enforcement

**Docker Socket Access:**
- Required for launching containers from within `langgraph-app` container
- Grants significant privileges - review security implications
- Consider dedicated MCP container launcher service for production

**Network Isolation:**
- stdio transport (no network exposure)
- Containers cannot access external network unless explicitly configured

**Resource Limits:**
```yaml
# Add to args in config.yaml
args:
  - "--memory=512m"      # Limit container memory
  - "--cpus=1.0"         # Limit CPU usage
  - "--cap-drop=ALL"     # Drop all Linux capabilities
```

### 9.8 Performance Considerations

**Startup Latency:**
- Container launch: 1-3 seconds per service
- Mitigated by long-lived connections (launched once at startup)

**Call Latency:**
- stdio transport: ~10-50ms overhead vs internal MCP
- File I/O: Dominated by actual operation (read/write), not transport
- JSON-RPC serialization: Negligible (<1ms)

**Concurrency:**
- Current: Sync wrapper blocks during async calls
- Future: Async migration enables parallel external MCP calls

**Best Practices:**
1. **Reuse connections**: Don't restart containers per request
2. **Batch operations**: Use internal iteration to minimize round-trips
3. **Monitor latency**: LangSmith traces show external MCP overhead
4. **Health checks**: Detect dead containers early (future enhancement)

### 9.9 Migration Path: Internal → External MCP

**Step 1: Dual Support (Fallback)**
```python
class FileOperationsSpecialist(BaseSpecialist):
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Try external MCP first
        if self.external_mcp_client:
            try:
                return self._external_file_operation(state)
            except Exception as e:
                logger.warning(f"External MCP failed, falling back to internal: {e}")

        # Fallback to internal MCP
        return self._internal_file_operation(state)
```

**Step 2: Gradual Migration**
- Start with non-critical operations (read_file)
- Monitor stability and performance
- Migrate write operations after validation

**Step 3: Deprecate Internal**
- Mark internal implementation as deprecated
- Remove fallback after external MCP proves stable

**Example: FileSpecialist Migration**
- **Current**: Internal Python MCP service
- **Future**: External filesystem MCP container
- **Benefit**: Reduced specialist count (ADR-CORE-013)

---

## 10.0 Adding New MCP Services (Automation)

**Problem:** Manually adding external MCP services requires editing multiple files, building Docker images, and updating configurations - error-prone and time-consuming.

**Solution:** The `add_mcp_service.py` script automates the entire process, enabling self-service addition of 310+ available dockerized MCP services.

### 10.1 Quick Start

**List Available Services:**
```bash
python scripts/add_mcp_service.py --list
```

**Install a Service:**
```bash
# Simple service (no API key required)
python scripts/add_mcp_service.py --service fetch

# Service requiring API key
python scripts/add_mcp_service.py --service brave-search

# Install as required service (fail-fast if unavailable)
python scripts/add_mcp_service.py --service postgres --required

# Auto-restart application after installation
python scripts/add_mcp_service.py --service fetch --auto-restart
```

### 10.2 How It Works

**Automation Workflow:**

```
┌────────────────────────────────────────────────────────┐
│ 1. Read Service Definition from Registry              │
│    config/mcp_registry.yaml                            │
│    - Package name (@modelcontextprotocol/server-fetch) │
│    - Environment variables needed                      │
│    - Docker args and volumes                           │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 2. Generate Dockerfile from Template                  │
│    docker/templates/node-mcp.Dockerfile                │
│    - Generic template works for all Node.js servers   │
│    - Build arg: NPM_PACKAGE                            │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 3. Build Docker Image                                  │
│    docker build -t mcp/fetch ...                       │
│    - Installs npm package globally                     │
│    - Creates entrypoint for stdio transport            │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 4. Update config.yaml (Atomic)                         │
│    - Create backup: config.yaml.backup                 │
│    - Write to temp: config.yaml.tmp                    │
│    - Atomic rename: tmp → config.yaml                  │
│    - Rollback capability if error occurs               │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 5. Update .env.example                                 │
│    - Add required environment variables                │
│    - Create MCP section if missing                     │
│    - Users copy values to .env                         │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 6. Display Next Steps                                  │
│    - List required env vars to add                     │
│    - Show restart command                              │
│    - Document service availability                     │
└────────────────────────────────────────────────────────┘
```

### 10.3 Available Services (Curated Registry)

The script uses a curated registry of known-good MCP servers. Current services:

| Service | Package | API Key Required | Description |
|---------|---------|------------------|-------------|
| `brave-search` | `@modelcontextprotocol/server-brave-search` | Yes (BRAVE_API_KEY) | Web search using Brave Search API |
| `fetch` | `@modelcontextprotocol/server-fetch` | No | HTTP fetching for web content |
| `puppeteer` | `@modelcontextprotocol/server-puppeteer` | No | Browser automation and web scraping |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | No | Secure file operations with directory boundaries |
| `postgres` | `@modelcontextprotocol/server-postgres` | Yes (POSTGRES_CONNECTION_STRING) | PostgreSQL database operations |
| `sqlite` | `@modelcontextprotocol/server-sqlite` | No | SQLite database operations |

**Registry Location:** `config/mcp_registry.yaml`

**Adding Custom Services:**

```yaml
# config/mcp_registry.yaml
available_servers:
  my-custom-service:
    source: "npm"
    package: "@org/server-name"
    dockerfile_template: "node-mcp"
    env_vars:
      - API_KEY
    args:
      - "--option=value"
    volumes:
      - "${WORKSPACE_PATH}/data:/data"
    description: "Custom service description"
    docs_url: "https://github.com/..."
```

### 10.4 Installation Example

**Installing Brave Search:**

```bash
$ python scripts/add_mcp_service.py --service brave-search

======================================================================
Installing MCP service: brave-search
======================================================================

Description: Web search using Brave Search API
Documentation: https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search

✓ Prerequisites validated
✓ Docker image 'mcp/brave-search' built successfully
✓ config.yaml updated with service 'brave-search'
  Backup saved to config.yaml.backup
✓ .env.example updated with environment variables

======================================================================
✓ Installation complete!
======================================================================

NEXT STEPS:
1. Add the following environment variables to your .env file:
   BRAVE_API_KEY=<your-api-key>

2. Restart the application:
   docker compose restart app

Service 'brave-search' is now available via external MCP!
Check config.yaml to verify configuration.
```

**Resulting Configuration:**

```yaml
# config.yaml (auto-generated)
mcp:
  external_mcp:
    enabled: true
    services:
      brave-search:
        enabled: true
        required: false
        command: "docker"
        args:
          - "run"
          - "-i"  # CRITICAL: maintains stdin for stdio transport
          - "--rm"
          - "-e"
          - "BRAVE_API_KEY=${BRAVE_API_KEY}"
          - "mcp/brave-search"
```

### 10.5 Language Independence

**Key Design Principle:** MCP + Docker abstracts language completely.

The same generic Dockerfile template works for:
- Node.js servers (via `npx`)
- Python servers (future: `python-mcp.Dockerfile`)
- Go binaries (future: `go-mcp.Dockerfile`)
- Pre-built containers (future: `prebuilt` template)

**Example Node.js Template:**

```dockerfile
# docker/templates/node-mcp.Dockerfile
ARG NPM_PACKAGE
FROM node:lts-alpine

# Install the MCP server package globally
RUN npm install -g ${NPM_PACKAGE}

# Create entrypoint that runs the MCP server
RUN echo '#!/bin/sh' > /usr/local/bin/mcp-server && \
    echo 'exec npx -y ${NPM_PACKAGE} "$@"' >> /usr/local/bin/mcp-server && \
    chmod +x /usr/local/bin/mcp-server

# MCP protocol uses stdin/stdout for JSON-RPC
ENTRYPOINT ["/usr/local/bin/mcp-server"]
CMD []
```

**Build Process:**

```bash
# Automatic build via script
docker build \
  --build-arg NPM_PACKAGE=@modelcontextprotocol/server-fetch \
  -f docker/templates/node-mcp.Dockerfile \
  -t mcp/fetch \
  .
```

### 10.6 Security & Validation

**Prerequisite Checks:**

1. **Docker Running:**
   ```bash
   docker ps  # Must succeed
   ```

2. **Template Exists:**
   ```bash
   ls docker/templates/node-mcp.Dockerfile  # Must exist
   ```

**Atomic Configuration Updates:**

```python
# Rollback-safe pattern (temp file + rename)
backup_path = config.yaml.backup
shutil.copy(config.yaml, backup_path)

temp_path = config.yaml.tmp
with open(temp_path, "w") as f:
    yaml.dump(config, f)

temp_path.replace(config.yaml)  # Atomic operation
```

**Failure Modes:**
- Docker build fails → No config changes made
- Config update fails → Backup available for rollback
- Template missing → Error before any changes

### 10.7 Offline/Fallback Resilience

**Progressive Resilience (MANDATE-CORE-001):**

The automation system supports offline operation:

1. **Local Docker Images:** Pre-built images work without internet
2. **Registry Caching:** `mcp_registry.yaml` cached locally
3. **Graceful Degradation:** Missing services don't break application
4. **Optional vs Required:** `required: false` allows partial availability

**Offline Workflow:**

```bash
# Pre-build images while online
python scripts/add_mcp_service.py --service fetch
python scripts/add_mcp_service.py --service sqlite

# Later, offline - images available from local Docker cache
docker compose up  # Works with pre-built images
```

### 10.8 Testing

**Unit Tests:** `app/tests/scripts/test_add_mcp_service.py`

```bash
# Run installer tests
python -m pytest app/tests/scripts/test_add_mcp_service.py -v

# Coverage includes:
# - Registry loading (2 tests)
# - Prerequisite validation (3 tests)
# - Docker image building (2 tests)
# - Config.yaml atomic updates (5 tests)
# - .env.example updates (3 tests)
# - Full installation workflow (5 tests)
# Total: 22 tests
```

**Test Coverage:**
- Registry loading and service info retrieval
- Prerequisite validation (Docker, templates)
- Docker image build success/failure
- Atomic config updates with rollback
- Environment variable updates
- Full installation workflow
- Error handling scenarios

### 10.9 Future Enhancements

**Potential Additions to Registry:**

- **Community Servers:**
  - Memory server (knowledge graph)
  - YouTube transcripts
  - Slack integration
  - DuckDuckGo search

- **Custom Templates:**
  - `python-mcp.Dockerfile` for Python servers
  - `go-mcp.Dockerfile` for Go binaries
  - `prebuilt.Dockerfile` for Docker Hub images

**Self-Service Addition:**

This automation enables **LAS self-modification** - the system could potentially add MCP services to itself based on user requests:

```
User: "I need PostgreSQL database access"
  ↓
Triage identifies need for postgres MCP service
  ↓
SystemsArchitect determines requirement
  ↓
ShellSpecialist executes: python scripts/add_mcp_service.py --service postgres
  ↓
System prompts user for POSTGRES_CONNECTION_STRING
  ↓
Application restarts with new capability
```

**Discovery vs Curated Registry:**

Current approach uses **curated registry** (known-good services). Future could support:
- Dynamic discovery from Docker Hub
- Community marketplace integration
- Security scanning before installation

---

## 11.0 Quick Reference

### Internal MCP (Python)
```python
# Call internal Python MCP service
result = self.mcp_client.call("file_specialist", "read_file", path="/workspace/data.txt")
```

### External MCP (Containers)
```python
# Call external containerized MCP service
result = sync_call_external_mcp(
    self.external_mcp_client,
    "filesystem",
    "read_file",
    {"path": "/projects/data.txt"}
)
```

### Service Discovery
```python
# Internal MCP
services = self.mcp_client.list_services()

# External MCP
services = self.external_mcp_client.get_connected_services()
tools = await self.external_mcp_client.list_tools("filesystem")
```

---

## 12.0 MCP Services vs Specialists

The system provides two distinct patterns for implementing MCP-accessible capabilities:

### 12.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Capabilities                          │
├─────────────────────────────────┬───────────────────────────────┤
│         SPECIALISTS             │           SERVICES            │
│  app/src/specialists/*.py       │   app/src/mcp/services/*.py   │
├─────────────────────────────────┼───────────────────────────────┤
│ ✓ Inherit from BaseSpecialist   │ ✗ Standalone classes          │
│ ✓ Have _execute_logic()         │ ✗ No graph execution          │
│ ✓ Can be routed to by Router    │ ✗ Never routed to             │
│ ✓ Can ALSO expose MCP services  │ ✓ ONLY MCP invocation         │
│ ✓ Managed by GraphBuilder       │ ✓ Registered explicitly       │
│ ✓ Can require LLM adapter       │ ✓ Can require LLM adapter     │
└─────────────────────────────────┴───────────────────────────────┘
```

### 12.2 When to Use Each Pattern

**Use a Specialist (in `app/src/specialists/`) when:**
- The capability needs to be routable by the RouterSpecialist
- It participates in graph execution workflows
- It needs to return state updates (`messages`, `artifacts`, etc.)
- It needs access to full `GraphState`
- Examples: `ChatSpecialist`, `ResearcherSpecialist`, `FileOperationsSpecialist`

**Use an MCP Service (in `app/src/mcp/services/`) when:**
- The capability is ONLY invoked directly by other components
- It should never be routed to by the graph
- It provides atomic operations without state management
- It's a standalone capability (vision, embedding, etc.)
- Examples: `FaraService` (visual UI verification)

### 12.3 Service Implementation Pattern

MCP Services are simpler than Specialists - they don't inherit from any base class:

```python
# app/src/mcp/services/my_service.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class MyService:
    """
    A standalone MCP service providing specific capabilities.

    This service is NOT a specialist - it cannot be routed to by the graph.
    It provides capabilities exclusively via MCP invocation.
    """

    # Optional dependencies (injected at construction)
    llm_adapter: Optional["BaseAdapter"] = None
    some_config: Dict[str, Any] = field(default_factory=dict)

    def my_operation(self, input: str) -> str:
        """An MCP-callable operation."""
        return f"Processed: {input}"

    def another_operation(self, data: Dict) -> Dict:
        """Another MCP-callable operation."""
        return {"result": data.get("value", 0) * 2}

    def register_mcp_services(self, registry: 'McpRegistry'):
        """Register this service's functions with MCP."""
        registry.register_service("my_service", {
            "my_operation": self.my_operation,
            "another_operation": self.another_operation,
        })
```

### 12.4 LLM-Requiring Services

Services can require an LLM adapter, making them "non-procedural" while still being service-only:

```python
# Example: FaraService (visual UI verification)

@dataclass
class FaraService:
    """
    Visual UI verification using Fara-7B vision model.

    This is an LLM-requiring service - it needs a vision model adapter
    but is NEVER routed to by the graph.
    """

    llm_adapter: Optional["BaseAdapter"] = None  # Vision model
    native_resolutions: Dict[str, Tuple[int, int]] = field(
        default_factory=lambda: {
            "square": (1024, 1024),
            "landscape": (1428, 896),
            "portrait": (896, 1428),
        }
    )

    def verify(self, element_description: str, screenshot_b64: Optional[str] = None) -> Dict:
        """
        Verify UI element presence using vision model.
        Requires llm_adapter to be set.
        """
        if not self.llm_adapter:
            raise ValueError("FaraService requires an LLM adapter (vision model)")

        # Scale image, call vision model, scale coordinates back
        # ... implementation ...
```

### 12.5 Service Registration

Services are registered during graph initialization, typically in `GraphBuilder`:

```python
# In GraphBuilder or application startup

from app.src.mcp.services import FaraService

# Create service instance with dependencies
fara_service = FaraService(
    llm_adapter=vision_adapter,  # From adapter factory
    native_resolutions=config.get("fara_resolutions", {})
)

# Register with MCP
fara_service.register_mcp_services(mcp_registry)
```

### 12.6 Calling Services

Services are called like any other MCP service:

```python
# From a specialist or other component
result = self.mcp_client.call("fara_service", "verify",
    element_description="Submit button",
    screenshot_b64=screenshot_data
)
```

### 12.7 Directory Structure

```
app/src/mcp/
├── __init__.py           # Exports McpRegistry, McpClient, etc.
├── registry.py           # McpRegistry implementation
├── client.py             # McpClient implementation
├── external_client.py    # ExternalMcpClient for containers
├── schemas.py            # McpRequest/McpResponse
└── services/             # Standalone MCP services
    ├── __init__.py       # Package exports
    └── fara_service.py   # Visual UI verification service
```

### 12.8 Decision Flowchart

```
                    ┌─────────────────────┐
                    │ New capability needed│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Needs graph routing? │
                    │ (RouterSpecialist   │
                    │  can route to it)   │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │ YES            │                │ NO
              ▼                │                ▼
    ┌─────────────────┐        │      ┌─────────────────┐
    │   SPECIALIST    │        │      │ Direct MCP only?│
    │ app/src/        │        │      │ (Never routed)  │
    │ specialists/    │        │      └────────┬────────┘
    └─────────────────┘        │               │
                               │      ┌────────┼────────┐
                               │      │ YES            │ NO
                               │      ▼                ▼
                               │ ┌─────────────┐  ┌─────────────┐
                               │ │  SERVICE    │  │ SPECIALIST  │
                               │ │ app/src/mcp/│  │ with MCP    │
                               │ │ services/   │  │ methods     │
                               │ └─────────────┘  └─────────────┘
```

**Key Questions:**
1. **Can the user ask for this directly?** → Specialist (routable)
2. **Is it only called by other code?** → Service
3. **Does it manage graph state?** → Specialist
4. **Is it a standalone atomic capability?** → Service

### 12.9 Current Services

| Service | Location | LLM Required | Description |
|---------|----------|--------------|-------------|
| `FaraService` | `app/src/mcp/services/fara_service.py` | Yes (Vision) | Visual UI verification using Fara-7B |

### 12.10 Migrating Specialists to Services

When refactoring an MCP-only specialist to a service:

1. **Remove BaseSpecialist inheritance** - Services are standalone
2. **Remove `_execute_logic()`** - Services don't participate in graph
3. **Keep `register_mcp_services()`** - This is the MCP interface
4. **Move to `app/src/mcp/services/`** - Correct location
5. **Update imports** - Export from `services/__init__.py`
6. **Update registration** - Register in `GraphBuilder` or startup

---

**For More Information:**
- **ADR-MCP-003**: [External MCP Container Integration](ADR/ADR-MCP-003-External-MCP-Container-Integration.md)
- **ADR-CORE-014**: [Async Graph Execution Migration](ADR/ADR-CORE-014-Async-Graph-Execution-Migration.md)
- **MCP Specification**: https://modelcontextprotocol.io/
- **MCP Python SDK**: https://github.com/modelcontextprotocol/python-sdk
- **Official MCP Servers**: https://github.com/modelcontextprotocol/servers
