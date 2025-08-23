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