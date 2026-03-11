# ADR-CORE-049: Operation Executor Pattern

## Status
Proposed

## Context

Specialists currently mix two concerns:
1. **Inference**: LLM decides *what* to do (parse user intent → structured operations)
2. **Execution**: Procedural code does *how* (call MCP, handle errors, iterate)

This coupling creates problems:
- `BatchProcessorSpecialist` hardcodes `move_file` calls - can't handle CREATE
- `FileOperationsSpecialist` does one operation then terminates
- Adding new operation types requires changing specialist logic
- Sync bridge (`sync_call_external_mcp`) is scattered across specialists

**Insight from prompt-prix**: The `TaskExecutor` pattern separates *what* (Task dataclass) from *how* (adapter dispatch), enabling backend-agnostic batch execution.

## Decision

**Proceduralize the procedural parts, using data from inference.**

Introduce a layered architecture:

### Layer 1: Operation Schema (the "what")

```python
from typing import Literal, Optional
from pydantic import BaseModel

class FileOperation(BaseModel):
    """Typed file operation - output of LLM inference."""
    type: Literal["read", "write", "move", "delete", "mkdir", "list"]
    path: str
    content: Optional[str] = None      # for write
    destination: Optional[str] = None  # for move
```

### Layer 2: Operation Executor (the "how")

```python
from typing import AsyncGenerator
from dataclasses import dataclass

@dataclass
class OperationResult:
    operation: FileOperation
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None

class FileOperationExecutor:
    """
    Backend-agnostic operation dispatcher.

    Specialists produce operation lists; executor handles MCP details.
    """

    def __init__(self, mcp_client: ExternalMcpClient):
        self.mcp_client = mcp_client

    async def execute(
        self,
        operations: list[FileOperation]
    ) -> AsyncGenerator[OperationResult, None]:
        """Execute operations, yielding results as they complete."""
        for op in operations:
            result = await self._dispatch(op)
            yield result

    async def _dispatch(self, op: FileOperation) -> OperationResult:
        """Dispatch single operation to MCP."""
        try:
            match op.type:
                case "write":
                    await self.mcp_client.call_tool(
                        "filesystem", "write_file",
                        {"path": op.path, "content": op.content or ""}
                    )
                    return OperationResult(op, success=True, result=f"Created {op.path}")

                case "read":
                    content = await self.mcp_client.call_tool(
                        "filesystem", "read_file", {"path": op.path}
                    )
                    return OperationResult(op, success=True, result=str(content))

                case "move":
                    await self.mcp_client.call_tool(
                        "filesystem", "move_file",
                        {"source": op.path, "destination": op.destination}
                    )
                    return OperationResult(op, success=True, result=f"Moved to {op.destination}")

                case "mkdir":
                    await self.mcp_client.call_tool(
                        "filesystem", "create_directory", {"path": op.path}
                    )
                    return OperationResult(op, success=True, result=f"Created directory {op.path}")

                case "list":
                    listing = await self.mcp_client.call_tool(
                        "filesystem", "list_directory", {"path": op.path}
                    )
                    return OperationResult(op, success=True, result=str(listing))

                case "delete":
                    # Note: filesystem MCP may not support delete
                    return OperationResult(op, success=False, error="Delete not supported")

        except Exception as e:
            return OperationResult(op, success=False, error=str(e))
```

### Layer 3: Specialist (inference only)

```python
class BatchProcessorSpecialist(BaseSpecialist):
    """
    Specialist produces typed operations; executor handles dispatch.
    """

    async def _execute_logic(self, state: dict) -> dict:
        # Phase 1: LLM parses intent → typed operations
        operations = await self._parse_operations(state["messages"])
        # Returns: [FileOperation(type="write", path="e.txt", content=""), ...]

        # Phase 2: Executor handles MCP dispatch
        executor = FileOperationExecutor(self.external_mcp_client)
        results = []
        async for result in executor.execute(operations):
            results.append(result)

        # Phase 3: Format response
        return self._format_results(results)

    async def _parse_operations(self, messages) -> list[FileOperation]:
        """LLM inference: user intent → operation list."""
        # Tool call with FileOperation schema
        # LLM returns structured list of operations
        pass
```

## Benefits

1. **Separation of concerns**: LLM does inference, procedural code does execution
2. **Extensibility**: New operation types added to schema + dispatch table, not specialist logic
3. **Async-native**: Aligns with ADR-CORE-014 async migration
4. **Testability**: Executor can be tested independently with mock MCP
5. **Reusability**: Same executor works for batch or single operations
6. **Observability**: Executor can log/trace all operations uniformly

## Migration Path

### Phase 1: Introduce FileOperationExecutor
- Create `app/src/executors/file_operation_executor.py`
- Define `FileOperation` schema in `app/src/specialists/schemas/`

### Phase 2: Refactor BatchProcessorSpecialist
- Replace hardcoded `move_file` calls with executor dispatch
- Add support for CREATE operations via `write` type

### Phase 3: Refactor FileOperationsSpecialist
- Use same executor for single operations
- Remove `task_is_complete: True` hardcoding

### Phase 4: Generalize pattern
- Consider `WebOperationExecutor` for browser operations
- Consider `ResearchOperationExecutor` for search/browse

## Relationship to Other ADRs

- **ADR-CORE-014**: Async migration - executor is async-native
- **ADR-CORE-035**: Filesystem consolidation - executor centralizes MCP access
- **ADR-MCP-003**: External MCP - executor wraps external MCP client

## Open Questions

1. Should executor handle retries, or leave to caller?
2. Parallel execution within a batch (asyncio.gather) vs sequential?
3. Should operation schemas be MCP-agnostic or MCP-aligned?

## References

- prompt-prix `TaskExecutor` pattern: `/prompt_prix/executor.py`
- prompt-prix `HostAdapter` protocol: `/prompt_prix/adapters/base.py`
