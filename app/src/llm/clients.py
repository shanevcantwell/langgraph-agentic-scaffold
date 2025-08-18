import logging
import os
import requests
import requests.exceptions
import json
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120

class LLMInvocationError(Exception):
    pass

def _is_retryable_gemini_exception(exception) -> bool:
    try:
        import google.api_core.exceptions
        return isinstance(exception, google.api_core.exceptions.ServiceUnavailable)
    except ImportError:
        return False

class BaseLLMClient(ABC):
    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> Dict[str, Any]:
        pass

class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str, system_prompt: Optional[str] = None):
        super().__init__(model)
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("The 'google-generativeai' package is required for Gemini.")
        
        genai.configure(api_key=api_key)
        self.genai_model = genai.GenerativeModel(model, system_instruction=system_prompt)
        logger.info(f"INITIALIZED GEMINI CLIENT (Model: {model})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=_is_retryable_gemini_exception,
        before_sleep=lambda retry_state: logger.warning(f"GEMINI RETRYING: {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> Dict[str, Any]:
        gemini_messages = [
            {"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]}
            for msg in messages
        ]

        logger.debug("CALLING GEMINI API")
        try:
            if tools:
                logger.debug("GeminiClient: Invoking in tool-calling mode.")
                response = self.genai_model.generate_content(
                    contents=gemini_messages,
                    generation_config={"temperature": temperature},
                    tools=tools,
                    request_options={"timeout": REQUEST_TIMEOUT}
                )
                # MODIFIED: Handle the tool call response
                if response.parts and hasattr(response.parts[0], 'function_call'):
                    function_call = response.parts[0].function_call
                    # Convert the google.protobuf.struct_pb2.Struct to a dict
                    args = dict(function_call.args)
                    logger.info(f"Gemini returned tool call '{function_call.name}' with args: {args}")
                    return args
                else:
                    raise LLMInvocationError("Tool call was expected, but none was returned by Gemini.")
            else:
                logger.debug("GeminiClient: Invoking in JSON-output mode.")
                response = self.genai_model.generate_content(
                    contents=gemini_messages,
                    generation_config={"temperature": temperature, "response_mime_type": "application/json"},
                    request_options={"timeout": REQUEST_TIMEOUT}
                )
            
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                raise LLMInvocationError(f"Gemini blocked prompt: {response.prompt_feedback.block_reason.name}")

            if not response.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                raise LLMInvocationError(f"Gemini returned an empty response. Finish Reason: {finish_reason}")

            response_content = response.text
            return json.loads(response_content)

        except json.JSONDecodeError as e:
            raise LLMInvocationError(f"Failed to parse Gemini response as JSON: {e}") from e
        except Exception as e:
            raise LLMInvocationError(f"An unexpected error occurred with Gemini API: {e}") from e

class OllamaClient(BaseLLMClient):
    """LLM client for a local Ollama instance."""
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        super().__init__(model)
        self.api_url = f"{base_url}/api/chat"
        logger.info(f"INITIALIZED OLLAMA CLIENT (Model: {self.model}, URL: {self.api_url})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: logger.warning(f"OLLAMA RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> Dict[str, Any]:
        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        payload = {
            "model": self.model,
            "messages": [{"role": role_map.get(msg.type, "user"), "content": msg.content} for msg in messages],
            "stream": False,
            "options": {"temperature": temperature},
            "format": "json"
        }
        
        logger.debug("CALLING OLLAMA API")
        response_content = ""
        try:
            response = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            response_content = response_data.get("message", {}).get("content", "")
            return json.loads(response_content)
        
        except json.JSONDecodeError as e:
            error_message = f"LLM Client Error: Failed to parse Ollama response as JSON. Details: {e}"
            logger.error(error_message)
            logger.debug(f"Invalid content received from Ollama: {response_content}")
            raise LLMInvocationError(error_message) from e
        except requests.exceptions.RequestException as e:
            error_message = f"Ollama network error: {e}"
            logger.error(error_message)
            raise LLMInvocationError(error_message) from e
        except Exception as e:
            error_message = f"An unexpected error occurred while calling the Ollama API: {e}"
            logger.error(error_message)
            raise LLMInvocationError(error_message) from e

class LMStudioClient(BaseLLMClient):
    """LLM client for a local LM Studio instance (OpenAI compatible)."""
    def __init__(self, model: str, base_url: str = "http://localhost:1234/v1"):
        super().__init__(model)
        self.api_url = f"{base_url}/chat/completions"
        logger.info(f"INITIALIZED LM STUDIO CLIENT (Model: {self.model}, URL: {self.api_url})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: logger.warning(f"LM STUDIO RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> Dict[str, Any]:
        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        payload = {
            "model": self.model,
            "messages": [{"role": role_map.get(msg.type, "user"), "content": msg.content} for msg in messages],
            "temperature": temperature,
        }
        
        logger.debug("CALLING LM STUDIO API")
        response_content = ""
        try:
            response = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            response_content = response_data['choices'][0]['message']['content']
            cleaned_content = re.sub(r"```(json)?\n(.*)\n```", r"\2", response_content, flags=re.DOTALL).strip()
            return json.loads(cleaned_content)

        except json.JSONDecodeError as e:
            error_message = f"LLM Client Error: Failed to parse LM Studio response as JSON. Details: {e}"
            logger.error(error_message)
            logger.debug(f"Invalid content received from LM Studio: {response_content}")
            raise LLMInvocationError(error_message) from e
        except requests.exceptions.RequestException as e:
            error_message = f"LM Studio network error: {e}"
            logger.error(error_message)
            raise LLMInvocationError(error_message) from e
        except Exception as e:
            error_message = f"An unexpected error occurred while calling the LM Studio API: {e}"
            logger.error(error_message)
            raise LLMInvocationError(error_message) from e
