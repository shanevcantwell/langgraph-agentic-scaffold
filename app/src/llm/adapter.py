from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class StandardizedLLMRequest(BaseModel):
    """A provider-agnostic request object that captures the specialist's runtime intent."""
    messages: List[BaseMessage]
    output_schema: Optional[Dict[str, Any]] = Field(default=None)

class BaseAdapter(ABC):
    """The abstract base class for all provider-specific adapters."""
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config

    @abstractmethod
    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        pass

class LLMInvocationError(Exception):
    pass
