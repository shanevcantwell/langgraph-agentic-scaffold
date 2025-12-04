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

if TYPE_CHECKING:
    from ..base import BaseSpecialist
    from ...llm.adapter import BaseAdapter, StandardizedLLMRequest
    from ...mcp.client import McpClient

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class MaxIterationsExceeded(Exception):
    """Raised when ReAct loop exceeds max_iterations without completing."""

    def __init__(self, iterations: int, history: List["ToolResult"]):
        self.iterations = iterations
        self.history = history
        super().__init__(
            f"ReAct loop exceeded {iterations} iterations without final response. "
            f"Tool history: {[h.tool_name for h in history]}"
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
    """

    # Type hints for expected attributes (provided by BaseSpecialist)
    llm_adapter: "BaseAdapter"
    mcp_client: Optional["McpClient"]

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

                # Execute the tool
                result = self._execute_tool(tool_call, tools, stop_on_error)
                tool_history.append(result)

                # Append result to messages for next LLM call
                working_messages.append(self._format_tool_result_message(result))

        # Exceeded max iterations
        raise MaxIterationsExceeded(max_iterations, tool_history)

    def _build_tool_schemas(self, tools: Dict[str, ToolDef]) -> List[Any]:
        """
        Build tool schemas in the format expected by the LLM adapter.

        Returns list of Pydantic model classes that the adapter will convert
        to JSON schemas for function calling.
        """
        # For now, we create simple schema classes dynamically
        # This could be enhanced to support more complex parameter schemas
        schemas = []

        for name, tool_def in tools.items():
            # Create a dynamic Pydantic model for the tool
            # The model name becomes the function name in the API
            description = tool_def.description or f"Call {tool_def.full_name}"

            # We need to create a proper Pydantic model class
            # For simplicity, we create a generic "args" parameter
            # In production, you'd want typed parameters per tool

            # Create class dynamically
            model = type(
                name,  # Class name = tool name
                (BaseModel,),
                {
                    "__doc__": description,
                    "__annotations__": {},
                    "model_config": {"extra": "allow"},  # Allow arbitrary kwargs
                }
            )
            schemas.append(model)

        return schemas

    def _execute_tool(
        self,
        tool_call: ToolCall,
        tools: Dict[str, ToolDef],
        stop_on_error: bool
    ) -> ToolResult:
        """
        Execute a single tool call via MCP.

        Args:
            tool_call: The tool call to execute
            tools: Tool definitions dict
            stop_on_error: Whether to raise on error

        Returns:
            ToolResult with success/error status
        """
        tool_name = tool_call.name

        if tool_name not in tools:
            error_msg = f"Unknown tool: {tool_name}. Available: {list(tools.keys())}"
            logger.warning(f"ReAct: {error_msg}")
            if stop_on_error:
                raise ToolExecutionError(tool_name, error_msg, [])
            return ToolResult(call=tool_call, success=False, error=error_msg)

        tool_def = tools[tool_name]

        if not hasattr(self, 'mcp_client') or self.mcp_client is None:
            error_msg = "MCP client not available"
            logger.warning(f"ReAct: {error_msg}")
            if stop_on_error:
                raise ToolExecutionError(tool_name, error_msg, [])
            return ToolResult(call=tool_call, success=False, error=error_msg)

        logger.debug(f"ReAct: Executing {tool_def.full_name} with args: {tool_call.args}")

        try:
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
