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
