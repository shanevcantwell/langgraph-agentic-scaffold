from abc import ABC, abstractmethod
import json
import re
from typing import List, Dict, Type, Any, Optional, cast
import html
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from ..utils.errors import LLMInvocationError, SafetyFilterError, RateLimitError, ProxyError

MAX_TOOL_CALLS = 10 # A reasonable upper limit for a single turn

class StandardizedLLMRequest(BaseModel):
    """A provider-agnostic request object that captures the specialist's runtime intent."""
    messages: List[BaseMessage]
    output_model_class: Optional[Type[BaseModel]] = Field(default=None)
    tools: Optional[List[Any]] = Field(default=None)
    force_tool_call: bool = Field(default=False, description="If True, forces the LLM to use a tool. Critical for routing.")
    image_data: Optional[str] = Field(default=None, description="Base64 encoded image data to attach to the last user message.")

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
        # Some local models, when instructed to return JSON containing an HTML
        # document, will incorrectly HTML-escape the string content of the
        # 'html_document' field. This method corrects that by un-escaping it.
        if 'html_document' in json_response and isinstance(json_response.get('html_document'), str):
            json_response['html_document'] = html.unescape(json_response['html_document'])
            
        return json_response

    def _robustly_parse_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Robustly extract a JSON object from text that may contain markdown fences
        or surrounding explanatory text.
        """
        if not isinstance(text, str):
            return None

        stripped = text.strip()

        # First prefer any fenced block content, regardless of declared language.
        # This handles valid JSON objects wrapped in ```json ... ``` or plain ``` ... ```.
        fenced_blocks = re.findall(r"```(?:[\w+-]+)?\s*(.*?)\s*```", stripped, re.DOTALL)
        for block in fenced_blocks:
            try:
                parsed = json.loads(block.strip())
                if isinstance(parsed, dict):
                    return cast(Dict[str, Any], parsed)
            except json.JSONDecodeError:
                continue

        # Try parsing the whole string directly.
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return cast(Dict[str, Any], parsed)
        except json.JSONDecodeError:
            pass

        # Fallback to finding the first JSON object in the text.
        try:
            start_index = stripped.find('{')
            end_index = stripped.rfind('}')
            if start_index != -1 and end_index != -1 and end_index > start_index:
                json_str = stripped[start_index:end_index+1]
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    return cast(Dict[str, Any], parsed)
        except (json.JSONDecodeError, IndexError):
            return None

        return None
