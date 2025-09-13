from abc import ABC, abstractmethod
from typing import List, Dict, Type, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from ..utils.errors import LLMInvocationError, SafetyFilterError, RateLimitError

MAX_TOOL_CALLS = 10 # A reasonable upper limit for a single turn

class StandardizedLLMRequest(BaseModel):
    """A provider-agnostic request object that captures the specialist's runtime intent."""
    messages: List[BaseMessage]
    output_model_class: Optional[Type[BaseModel]] = Field(default=None)
    tools: Optional[List[Any]] = Field(default=None)
    force_tool_call: bool = Field(default=False, description="If True, forces the LLM to use a tool. Critical for routing.")

class BaseAdapter(ABC):
    """
    The abstract base class for all provider-specific adapters.
    """
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config
        self.model_name: Optional[str] = model_config.get("api_identifier")

    @property
    @abstractmethod
    def api_base(self) -> Optional[str]:
        """The base URL for the API, if applicable."""
        pass

    @property
    @abstractmethod
    def api_key(self) -> Optional[str]:
        """The API key for the provider, if applicable."""
        pass

    @classmethod
    @abstractmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "BaseAdapter":
        """
        A factory class method to create an instance of the adapter from a
        configuration dictionary. Each concrete adapter must implement this.

        Args:
            provider_config: The specific configuration block for this provider from `llm_providers`.
            system_prompt: The system prompt to be used by the adapter instance.
        """
        pass

    @abstractmethod
    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        pass

    def _post_process_json_response(self, json_response: Dict[str, Any], output_model_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
        """
        Hook for adapters to post-process JSON responses before Pydantic validation.
        Default implementation returns the response as is.
        Subclasses can override this for specific schema transformations.
        """
        return json_response
