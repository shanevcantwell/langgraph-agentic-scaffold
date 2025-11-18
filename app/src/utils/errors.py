class SpecialistError(Exception):
    """Custom exception for errors that occur within a specialist's execution.

    This allows for more specific error handling in the main graph.
    """
    pass

class ConfigError(Exception):
    """Custom exception for errors related to configuration validation."""
    pass

class LLMInvocationError(Exception):
    """Base exception for LLM invocation errors."""
    pass

class SafetyFilterError(LLMInvocationError):
    """Raised when the LLM response is blocked by safety filters."""
    pass

class RateLimitError(LLMInvocationError):
    """Raised when the LLM provider returns a rate limit error (e.g., 429)."""
    pass

class ProxyError(LLMInvocationError):
    """Raised when a connection is blocked by a proxy."""
    pass

class WorkflowError(Exception):
    """Custom exception for errors that occur within the overall workflow execution."""
    pass

class SpecialistLoadError(Exception):
    """Custom exception for errors that occur during specialist loading."""
    pass

class McpError(Exception):
    """Base exception for MCP (Message-Centric Protocol) related errors."""
    pass

class McpServiceNotFoundError(McpError):
    """Raised when requested MCP service doesn't exist in the registry."""
    pass

class McpFunctionNotFoundError(McpError):
    """Raised when requested function doesn't exist in the MCP service."""
    pass

class McpInvocationError(McpError):
    """Raised when MCP function execution fails."""
    pass

class InvariantViolationError(Exception):
    """Raised when a system invariant is violated."""
    pass