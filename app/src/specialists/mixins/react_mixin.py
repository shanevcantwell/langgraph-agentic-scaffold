# app/src/specialists/mixins/react_mixin.py
"""
ReActMixin - Iterative tool use capability for specialists.

Enables specialists to perform ReAct-style loops:
  LLM → tool → LLM → tool → ... → final answer

This is distinct from the existing patterns:
  - BatchProcessor: LLM plans once, procedural execution
  - Graph routing: Each tool call is a separate graph node

ReActMixin keeps the loop internal to a single specialist execution,
which is ideal for tight iteration with visual tools (Fara), debugging,
or any scenario where the LLM needs to see tool results and decide next steps.

Usage:
    class MySpecialist(BaseSpecialist, ReActMixin):
        def _execute_logic(self, state):
            tools = {
                "screenshot": ToolDef(service="fara", function="screenshot"),
                "verify": ToolDef(service="fara", function="verify_element"),
                "click": ToolDef(service="fara", function="click"),
            }

            final_response, history = self.execute_with_tools(
                messages=state["messages"],
                tools=tools,
                max_iterations=15
            )

            return {
                "artifacts": {"react_trace": [h.model_dump() for h in history]},
                "messages": [AIMessage(content=final_response)]
            }
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage

# External MCP support for filesystem operations
from ...mcp import sync_call_external_mcp, extract_text_from_mcp_result

# Cycle detection for stagnation (Issue #78)
from ...resilience.cycle_detection import detect_cycle_with_pattern

if TYPE_CHECKING:
    from ..base import BaseSpecialist
    from ...llm.adapter import BaseAdapter, StandardizedLLMRequest
    from ...mcp.client import McpClient

logger = logging.getLogger(__name__)


# =============================================================================
# Module-level helpers (don't require injection for config-driven ReAct)
# =============================================================================

def _enrich_filesystem_error(
    error_msg: str,
    failed_path: str,
    successful_paths: List[str]
) -> str:
    """
    Enrich filesystem errors with context from successful prior calls.

    When a model gets ENOENT or similar errors, it often doesn't understand
    why or how to recover. If we've seen successful calls to similar paths,
    we can hint at what might have gone wrong.

    Args:
        error_msg: The original error message
        failed_path: The path that failed
        successful_paths: List of paths that worked earlier

    Returns:
        Enriched error message with recovery hints
    """
    # Only enrich common filesystem errors
    enrichable_errors = ["ENOENT", "EISDIR", "EACCES", "ENOTDIR"]
    if not any(err in error_msg for err in enrichable_errors):
        return error_msg

    if not successful_paths:
        return error_msg

    # Find paths that look similar to the failed one
    failed_basename = failed_path.split('/')[-1] if '/' in failed_path else failed_path
    similar = []
    for p in successful_paths:
        # Check if failed path is a suffix of successful path (forgot directory)
        if p.endswith(failed_path) or p.endswith(f"/{failed_path}"):
            similar.append(p)
        # Check if same filename in different directory
        elif failed_basename and p.endswith(f"/{failed_basename}"):
            similar.append(p)

    if similar:
        # Use the most recent similar path
        hint = f"\n\nHint: You previously succeeded with: {similar[-1]}"
        hint += f"\nDid you forget the directory prefix?"
        return error_msg + hint

    return error_msg


def _enrich_list_directory_result(result: str, queried_path: str) -> str:
    """
    Prepend directory path to list_directory entries for unambiguous paths.

    Raw MCP returns: "[FILE] c.txt"
    Enriched output: "[FILE] sort_by_contents/c.txt"

    This matches Facilitator's gathered_context format, ensuring the model
    sees consistent paths regardless of context source (ADR-ROADMAP-001:
    Facilitator operates in token space - precise context construction).
    """
    if not queried_path:
        return result  # No path to prepend

    lines = result.split('\n')
    enriched = []
    for line in lines:
        if line.startswith('[DIR] '):
            name = line[6:]  # len('[DIR] ') = 6
            enriched.append(f"[DIR] {queried_path}/{name}")
        elif line.startswith('[FILE] '):
            name = line[7:]  # len('[FILE] ') = 7
            enriched.append(f"[FILE] {queried_path}/{name}")
        elif line.strip():
            # Unknown format - still prepend path
            enriched.append(f"{queried_path}/{line}")
        else:
            enriched.append(line)  # Preserve empty lines
    return '\n'.join(enriched)


# =============================================================================
# Exceptions
# =============================================================================

class ReActLoopTerminated(Exception):
    """Base exception for ReAct loop termination conditions."""

    def __init__(self, message: str, iterations: int, history: List["ToolResult"]):
        self.iterations = iterations
        self.history = history
        super().__init__(message)


class MaxIterationsExceeded(ReActLoopTerminated):
    """Raised when ReAct loop exceeds max_iterations without completing."""

    def __init__(self, iterations: int, history: List["ToolResult"]):
        super().__init__(
            f"ReAct loop exceeded {iterations} iterations without final response. "
            f"Tool history: {[h.tool_name for h in history]}",
            iterations,
            history
        )


class StagnationDetected(ReActLoopTerminated):
    """Raised when ReAct loop detects repeated identical tool calls (no progress)."""

    def __init__(
        self,
        tool_name: str,
        args: Dict[str, Any],
        repeat_count: int,
        iterations: int,
        history: List["ToolResult"]
    ):
        self.tool_name = tool_name
        self.args = args
        self.repeat_count = repeat_count
        super().__init__(
            f"Stagnation detected: '{tool_name}' called {repeat_count} times "
            f"with identical args {args}. Loop terminated to prevent waste.",
            iterations,
            history
        )


class ToolExecutionError(Exception):
    """Raised when a tool call fails during ReAct execution."""

    def __init__(self, tool_name: str, error: str, history: List["ToolResult"]):
        self.tool_name = tool_name
        self.error = error
        self.history = history
        super().__init__(f"Tool '{tool_name}' failed: {error}")


# =============================================================================
# Schemas
# =============================================================================

class ToolDef(BaseModel):
    """Definition of an MCP tool available to the ReAct loop."""
    service: str = Field(..., description="MCP service name (e.g., 'fara', 'file_specialist')")
    function: str = Field(..., description="Function name within the service")
    description: Optional[str] = Field(None, description="Human-readable description for LLM")

    @property
    def full_name(self) -> str:
        """Returns 'service.function' format."""
        return f"{self.service}.{self.function}"


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""
    id: str = Field(..., description="Unique identifier for this tool call")
    name: str = Field(..., description="Tool name (matches key in tools dict)")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")


class ToolResult(BaseModel):
    """Result of executing a tool call."""
    call: ToolCall = Field(..., description="The original tool call")
    success: bool = Field(..., description="Whether the tool executed successfully")
    result: Any = Field(None, description="Tool return value (if success)")
    error: Optional[str] = Field(None, description="Error message (if failure)")

    @property
    def tool_name(self) -> str:
        return self.call.name


# =============================================================================
# ReActMixin
# =============================================================================

class ReActMixin:
    """
    Mixin that adds iterative tool use capability to specialists.

    Requires the specialist to have:
    - self.llm_adapter: BaseAdapter instance
    - self.mcp_client: McpClient instance (optional, for MCP-based tools)

    The mixin provides execute_with_tools() which runs a ReAct loop:
    1. Send messages + tool definitions to LLM
    2. If LLM returns tool_calls, execute them via MCP
    3. Append tool results to messages, loop back to step 1
    4. If LLM returns text (no tool_calls), return as final response

    Stagnation detection (inspired by invariants.py):
    - Tracks recent tool call signatures (name + args hash)
    - If same call repeated STAGNATION_THRESHOLD times, raises StagnationDetected
    - Allows productive loops (varied calls) while catching stuck loops fast
    """

    # Type hints for expected attributes (provided by BaseSpecialist)
    llm_adapter: "BaseAdapter"
    mcp_client: Optional["McpClient"]

    # Cycle detection: detect repeating patterns in tool calls (Issue #78)
    # Catches both identical calls (A-A-A) and cyclic patterns (A-B-C-D-A-B-C-D)
    CYCLE_MIN_REPETITIONS = 2  # Cycle must repeat at least this many times

    # Tool parameter schemas for proper function calling
    # Maps tool name -> dict of {param_name: (type, Field(...))}
    # This enables LLMs to distinguish between tools with different signatures
    TOOL_PARAMETERS: Dict[str, Dict[str, tuple]] = {
        # Filesystem tools (external MCP)
        "list_directory": {
            "path": (str, Field(description="Directory path to list"))
        },
        "read_file": {
            "path": (str, Field(description="File path to read"))
        },
        "move_file": {
            "source": (str, Field(description="Source file path")),
            "destination": (str, Field(description="Destination file path"))
        },
        "create_directory": {
            "path": (str, Field(description="Directory path to create"))
        },
        "write_file": {
            "path": (str, Field(description="File path to write")),
            "content": (str, Field(description="Content to write to file"))
        },
        # Web research tools (internal MCP)
        "search": {
            "query": (str, Field(description="Search query string"))
        },
        "browse": {
            "url": (str, Field(description="URL to fetch and parse"))
        },
        # Terminal tools (external MCP - ADR-MCP-005)
        "run_command": {
            "command": (str, Field(description="Shell command to execute (allowlist: pwd, ls, cat, head, tail, grep, etc.)"))
        },
    }

    def execute_with_tools(
        self,
        messages: List[BaseMessage],
        tools: Dict[str, ToolDef],
        max_iterations: int = 10,
        stop_on_error: bool = False,
    ) -> Tuple[str, List[ToolResult]]:
        """
        Execute a ReAct loop with the given tools.

        Args:
            messages: Initial conversation messages
            tools: Dict mapping tool names to ToolDef objects
            max_iterations: Maximum number of LLM calls before raising
            stop_on_error: If True, raise on first tool error. If False, report error to LLM.

        Returns:
            Tuple of (final_response: str, tool_history: List[ToolResult])

        Raises:
            MaxIterationsExceeded: If loop doesn't complete within max_iterations
            ToolExecutionError: If stop_on_error=True and a tool fails
            ValueError: If llm_adapter is not set
        """
        if not hasattr(self, 'llm_adapter') or self.llm_adapter is None:
            raise ValueError("ReActMixin requires llm_adapter to be set")

        # Build tool schemas for LLM
        tool_schemas = self._build_tool_schemas(tools)

        # Working copy of messages (we'll append tool results)
        working_messages = list(messages)
        tool_history: List[ToolResult] = []

        # Stagnation detection: track recent call signatures
        recent_call_signatures: List[tuple] = []

        # Error enrichment: track successful filesystem paths for recovery hints
        successful_paths: List[str] = []

        logger.info(f"ReAct: Starting loop with {len(tools)} tools, max_iterations={max_iterations}")

        for iteration in range(max_iterations):
            logger.debug(f"ReAct: Iteration {iteration + 1}/{max_iterations}")

            # Call LLM
            from ..base import BaseSpecialist
            from ...llm.adapter import StandardizedLLMRequest

            request = StandardizedLLMRequest(
                messages=working_messages,
                tools=tool_schemas if tool_schemas else None,
            )

            response = self.llm_adapter.invoke(request)

            # Check if LLM returned tool calls
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # No tool calls = final response
                final_text = response.get("text_response", "")
                logger.info(f"ReAct: Completed after {iteration + 1} iterations, {len(tool_history)} tool calls")
                return final_text, tool_history

            # Execute tool calls
            for tc in tool_calls:
                tool_call = ToolCall(
                    id=tc.get("id", f"call_{iteration}_{len(tool_history)}"),
                    name=tc.get("name", ""),
                    args=tc.get("args", {})
                )

                # Execute the tool (pass successful_paths for error enrichment)
                result = self._execute_tool(tool_call, tools, stop_on_error, successful_paths)
                tool_history.append(result)

                # Track successful filesystem paths for error recovery hints
                if result.success and tool_call.name in ("list_directory", "read_file", "move_file"):
                    path = tool_call.args.get("path") or tool_call.args.get("source")
                    if path:
                        successful_paths.append(path)

                # Stagnation detection: compute call signature and check for repeats
                call_signature = self._compute_call_signature(tool_call)
                recent_call_signatures.append(call_signature)

                # Cycle detection: catch both identical calls (A-A-A) and cyclic patterns (A-B-C-D-A-B-C-D)
                # This addresses Issue #78 - batch operations create cycles with period = batch size
                # Use getattr for compatibility with injected execute_with_tools (ADR-CORE-051)
                min_reps = getattr(self, 'CYCLE_MIN_REPETITIONS', 2)
                period, pattern = detect_cycle_with_pattern(
                    recent_call_signatures,
                    min_repetitions=min_reps
                )
                if period is not None:
                    logger.warning(
                        f"ReAct: Cycle detected - period {period} pattern repeated "
                        f"{min_reps} times: {pattern}"
                    )
                    raise StagnationDetected(
                        tool_name=tool_call.name,
                        args=tool_call.args,
                        repeat_count=period * min_reps,
                        iterations=iteration + 1,
                        history=tool_history
                    )

                # Append result to messages for next LLM call
                working_messages.append(self._format_tool_result_message(result))

        # Exceeded max iterations
        raise MaxIterationsExceeded(max_iterations, tool_history)

    def _build_tool_schemas(self, tools: Dict[str, ToolDef]) -> List[Any]:
        """
        Build tool schemas in the format expected by the LLM adapter.

        Returns list of Pydantic model classes that the adapter will convert
        to JSON schemas for function calling.

        Uses TOOL_PARAMETERS registry to generate proper typed parameters,
        enabling LLMs to distinguish between tools with different signatures.
        """
        schemas = []

        for name, tool_def in tools.items():
            description = tool_def.description or f"Call {tool_def.full_name}"

            # Look up parameter definitions from registry
            param_defs = self.TOOL_PARAMETERS.get(name, {})

            if param_defs:
                # Build proper annotations and field defaults
                annotations = {}
                namespace = {"__doc__": description, "model_config": {"extra": "forbid"}}

                for param_name, (param_type, field_info) in param_defs.items():
                    annotations[param_name] = param_type
                    namespace[param_name] = field_info

                namespace["__annotations__"] = annotations

                model = type(name, (BaseModel,), namespace)
            else:
                # Fallback for unknown tools: allow arbitrary kwargs
                # Log a warning so we can add missing tools to the registry
                logger.warning(
                    f"ReAct: Tool '{name}' not in TOOL_PARAMETERS registry. "
                    f"Using permissive schema - LLM may have difficulty with parameters."
                )
                model = type(
                    name,
                    (BaseModel,),
                    {
                        "__doc__": description,
                        "__annotations__": {},
                        "model_config": {"extra": "allow"},
                    }
                )

            schemas.append(model)

        return schemas

    def _compute_call_signature(self, tool_call: ToolCall) -> tuple:
        """
        Compute a hashable signature for a tool call (name + sorted args).

        Used for stagnation detection - identical signatures indicate
        the LLM is making the same call repeatedly without progress.

        Returns:
            Tuple of (tool_name, tuple of sorted (key, value) pairs)
        """
        # Sort args to ensure consistent ordering
        sorted_args = tuple(sorted(tool_call.args.items()))
        return (tool_call.name, sorted_args)

    # Services that require external MCP (containerized)
    # These are defined in config.yaml under mcp.external_mcp.services
    EXTERNAL_MCP_SERVICES = {"filesystem", "terminal"}

    def _execute_tool(
        self,
        tool_call: ToolCall,
        tools: Dict[str, ToolDef],
        stop_on_error: bool,
        successful_paths: Optional[List[str]] = None
    ) -> ToolResult:
        """
        Execute a single tool call via MCP.

        Routes to external MCP for containerized services (filesystem)
        and internal MCP for Python-based specialists.

        Args:
            tool_call: The tool call to execute
            tools: Tool definitions dict
            stop_on_error: Whether to raise on error
            successful_paths: List of paths that worked earlier (for error hints)

        Returns:
            ToolResult with success/error status
        """
        successful_paths = successful_paths or []
        tool_name = tool_call.name

        if tool_name not in tools:
            error_msg = f"Unknown tool: {tool_name}. Available: {list(tools.keys())}"
            logger.warning(f"ReAct: {error_msg}")
            if stop_on_error:
                raise ToolExecutionError(tool_name, error_msg, [])
            return ToolResult(call=tool_call, success=False, error=error_msg)

        tool_def = tools[tool_name]
        is_external = tool_def.service in self.EXTERNAL_MCP_SERVICES

        # Check for required MCP client
        if is_external:
            if not hasattr(self, 'external_mcp_client') or self.external_mcp_client is None:
                error_msg = f"External MCP client not available for service '{tool_def.service}'"
                logger.warning(f"ReAct: {error_msg}")
                if stop_on_error:
                    raise ToolExecutionError(tool_name, error_msg, [])
                return ToolResult(call=tool_call, success=False, error=error_msg)
        else:
            if not hasattr(self, 'mcp_client') or self.mcp_client is None:
                error_msg = "Internal MCP client not available"
                logger.warning(f"ReAct: {error_msg}")
                if stop_on_error:
                    raise ToolExecutionError(tool_name, error_msg, [])
                return ToolResult(call=tool_call, success=False, error=error_msg)

        logger.debug(f"ReAct: Executing {tool_def.full_name} with args: {tool_call.args} (external={is_external})")

        try:
            if is_external:
                # External MCP: containerized services (filesystem)
                raw_result = sync_call_external_mcp(
                    self.external_mcp_client,
                    tool_def.service,
                    tool_def.function,
                    tool_call.args
                )
                # Extract text content from MCP CallToolResult object
                # Without this, LLM sees object repr instead of actual content
                result = extract_text_from_mcp_result(raw_result)

                # Enrich list_directory results with full paths
                # Ensures consistency with Facilitator's gathered_context format
                if tool_def.function == "list_directory":
                    queried_path = tool_call.args.get("path", "")
                    result = _enrich_list_directory_result(result, queried_path)
            else:
                # Internal MCP: Python specialists
                result = self.mcp_client.call(
                    tool_def.service,
                    tool_def.function,
                    **tool_call.args
                )
            logger.debug(f"ReAct: {tool_name} returned: {str(result)[:200]}...")
            return ToolResult(call=tool_call, success=True, result=result)

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"ReAct: Tool {tool_name} failed: {error_msg}")

            # Enrich filesystem errors with recovery hints
            if is_external and tool_def.service == "filesystem":
                failed_path = tool_call.args.get("path") or tool_call.args.get("source") or ""
                error_msg = _enrich_filesystem_error(error_msg, failed_path, successful_paths)

            if stop_on_error:
                raise ToolExecutionError(tool_name, error_msg, [])
            return ToolResult(call=tool_call, success=False, error=error_msg)

    def _format_tool_result_message(self, result: ToolResult) -> ToolMessage:
        """
        Format a tool result as a LangChain ToolMessage for the conversation.
        """
        if result.success:
            content = str(result.result)
        else:
            content = f"Error: {result.error}"

        return ToolMessage(
            content=content,
            tool_call_id=result.call.id,
            name=result.call.name
        )
