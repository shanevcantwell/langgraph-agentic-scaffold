from abc import ABC, abstractmethod
from typing import List, Dict, Type, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from ..utils.errors import LLMInvocationError, SafetyFilterError, RateLimitError

class StandardizedLLMRequest(BaseModel):
    """A provider-agnostic request object that captures the specialist's runtime intent."""
    messages: List[BaseMessage]
    output_model_class: Optional[Type[BaseModel]] = Field(default=None)
    tools: Optional[List[Any]] = Field(default=None)

class BaseAdapter(ABC):
    """
    The abstract base class for all provider-specific adapters.
    """
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config

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
