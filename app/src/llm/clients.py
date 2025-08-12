import logging
import os
import requests
import requests.exceptions
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Using langchain_core.messages for consistency with the graph state
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

def _is_retryable_gemini_exception(exception) -> bool:
    """Return True if the exception is a retryable Gemini API error."""
    try:
        import google.api_core.exceptions
        return isinstance(exception, google.api_core.exceptions.ServiceUnavailable)
    except ImportError:
        # If google-api-core is not installed, it can't be this exception.
        return False

class BaseLLMClient(ABC):
    """
    Abstract base class for all LLM clients, defining a standard interface
    for making API calls.
    """
    @abstractmethod
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = None) -> AIMessage:
        """
        Sends a list of messages to the LLM and returns the response.

        Args:
            messages (List[BaseMessage]): A list of messages forming the conversation
                                          history and prompt.

            tools (Optional[List[Any]]): An optional list of tools for the LLM.
            temperature (Optional[float]): The sampling temperature to use.
        Returns:
            AIMessage: The response from the language model.
        """
        pass

class GeminiClient(BaseLLMClient):
    """LLM client for Google's Gemini API."""
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("The 'google-generativeai' package is required for Gemini. Please install it with 'pip install google-generativeai'.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        logger.info(f"INITIALIZED GEMINI CLIENT (Model: {model})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=_is_retryable_gemini_exception,
        before_sleep=lambda retry_state: logger.warning(f"GEMINI RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        gemini_messages = [
            {"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]}
            for msg in messages if not isinstance(msg, SystemMessage)
        ]
        system_prompt = next((msg.content for msg in messages if isinstance(msg, SystemMessage)), None)
        
        logger.debug("CALLING GEMINI API")

        gemini_messages = []
        system_instructions = []

        # Separate system messages and other messages
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_instructions.append(msg.content)
            else:
                gemini_messages.append({"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]})

        # Always include a system instruction for JSON output
        json_system_instruction = "Your response MUST be a valid JSON object. Do NOT include any other text or explanations."
        system_instructions.insert(0, json_system_instruction) # Prepend the JSON instruction

        # Combine all system instructions into a single string
        combined_system_instruction = "\n".join(system_instructions)

        # Prepend the combined system instruction to the first user message
        if gemini_messages and gemini_messages[0]['role'] == 'user':
            gemini_messages[0]['parts'].insert(0, combined_system_instruction)
        elif not gemini_messages:
            # If no messages, just add the system instruction as a user message (Gemini limitation)
            gemini_messages.append({"role": "user", "parts": [combined_system_instruction]})
        else:
            # If the first message is not a user message, add a new user message with the instruction
            gemini_messages.insert(0, {"role": "user", "parts": [combined_system_instruction]})
        
        logger.debug("CALLING GEMINI API")

        try:
            gemini_tools = []
            if tools:
                for tool_obj in tools:
                    tool_schema = {
                        "function_declarations": [
                            {
                                "name": tool_obj.name,
                                "description": tool_obj.description,
                                "parameters": tool_obj.args_schema.schema()
                            }
                        ]
                    }
                    gemini_tools.append(tool_schema)

            response = self.model.generate_content(
                contents=gemini_messages,
                generation_config={
                    "temperature": temperature
                },
                tools=gemini_tools if gemini_tools else None,
                request_options={
                    "timeout": 60
                }
            )
            
            # --- Robust Response Handling ---
            # Check for prompt feedback blocking first
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
                return AIMessage(content=f"Error: Gemini blocked the prompt due to: {block_reason}")

            # Check for tool calls
            tool_calls = []
            if response.parts:
                for part in response.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "args": {k: v for k, v in part.function_call.args.items()}
                        })
            if tool_calls:
                return AIMessage(content="", tool_calls=tool_calls)

            # Attempt to get text content
            text_content = ""
            if hasattr(response, 'text'):
                try:
                    text_content = response.text
                except ValueError:
                    # This handles cases where .text might raise ValueError if no text is present
                    pass

            if text_content:
                return AIMessage(content=text_content)
            else:
                # If no text content, check finish reason for more details
                finish_reason = None
                if response.candidates and response.candidates[0].finish_reason:
                    finish_reason = response.candidates[0].finish_reason.name

                if finish_reason and finish_reason != "STOP":
                    return AIMessage(content=f"Error: Gemini finished with reason: {finish_reason} and no text content.")
                else:
                    # Fallback for empty or unexpected responses, or STOP with no text
                    return AIMessage(content="Error: Gemini returned an empty or unexpected response.")

        except Exception as e:
            logger.error(f"An error occurred while calling the Gemini API: {e}")
            return AIMessage(content=f"Error: Could not get a response from Gemini. Details: {e}")

class OllamaClient(BaseLLMClient):
    """LLM client for a local Ollama instance."""
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.api_url = f"{base_url}/api/chat"
        logger.info(f"INITIALIZED OLLAMA CLIENT (Model: {self.model}, URL: {self.api_url})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: logger.warning(f"OLLAMA RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        # Map LangChain message types to Ollama roles
        role_map = {"human": "user", "ai": "assistant", "system": "system"}

        payload = {
            "model": self.model,
            "messages": [{
                "role": role_map.get(msg.type, "user"),
                "content": msg.content
            } for msg in messages],
            "stream": False,
            "options": {
                "temperature": temperature
            },
            "format": "json"
        }
        logger.debug("CALLING OLLAMA API")
        response = requests.post(self.api_url, json=payload)
        response.raise_for_status()
        response_data = response.json()
        
        content = response_data.get("message", {}).get("content", "")
        return AIMessage(content=content)

class LMStudioClient(BaseLLMClient):
    """LLM client for a local LM Studio instance (OpenAI compatible)."""
    def __init__(self, model: str, base_url: str = "http://localhost:1234/v1"):
        self.model = model
        self.api_url = f"{base_url}/chat/completions"
        logger.info(f"INITIALIZED LM STUDIO CLIENT (Model: {self.model}, URL: {self.api_url})")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: logger.warning(f"LM STUDIO RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        # Map LangChain message types to OpenAI-compatible roles
        role_map = {"human": "user", "ai": "assistant", "system": "system"}

        payload = {
            "model": self.model,
            "messages": [{
                "role": role_map.get(msg.type, "user"),
                "content": msg.content
            } for msg in messages],
            "temperature": temperature,
        }
        logger.debug("CALLING LM STUDIO API")
        response = requests.post(self.api_url, json=payload)
        response.raise_for_status()
        response_data = response.json()

        content = response_data['choices'][0]['message']['content']
        return AIMessage(content=content)
