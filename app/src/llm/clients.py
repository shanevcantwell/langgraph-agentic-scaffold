# src/llm/clients.py

import os
import requests
import requests.exceptions
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import google.api_core.exceptions
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Using langchain_core.messages for consistency with the graph state
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage

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
        print(f"---INITIALIZED GEMINI CLIENT (Model: {model})---")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(google.api_core.exceptions.ServiceUnavailable),
        before_sleep=lambda retry_state: print(f"---GEMINI RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}---")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        gemini_messages = [
            {"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]}
            for msg in messages if not isinstance(msg, SystemMessage)
        ]
        system_prompt = next((msg.content for msg in messages if isinstance(msg, SystemMessage)), None)
        
        print(f"---CALLING GEMINI API---")

        # Always include a system instruction for JSON output
        json_system_instruction = "Your response MUST be a valid JSON object. Do NOT include any other text or explanations."
        
        # Prepend the JSON instruction to the messages
        if gemini_messages and gemini_messages[0]['role'] == 'user':
            # If there's an existing system prompt, combine it with the JSON instruction
            if system_prompt:
                gemini_messages[0]['parts'] = [json_system_instruction + "\n" + system_prompt, gemini_messages[0]['parts'][0]]
            else:
                gemini_messages[0]['parts'] = [json_system_instruction, gemini_messages[0]['parts'][0]]
        elif not gemini_messages:
            # If no messages, just add the system instruction as a user message (Gemini limitation)
            gemini_messages.append({"role": "user", "parts": [json_system_instruction]})
        else:
            # If the first message is not a user message, add a new user message with the instruction
            gemini_messages.insert(0, {"role": "user", "parts": [json_system_instruction]})

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
                gemini_messages,
                generation_config={"temperature": temperature},
                tools=gemini_tools if gemini_tools else None,
                request_options={"timeout": 60}
            )
            
            # --- Robust Response Handling ---
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                return AIMessage(content=f"Error: Gemini blocked the prompt due to: {response.prompt_feedback.block_reason.name}")

            if response.parts:
                # Handle tool calls
                tool_calls = []
                for part in response.parts:
                    if part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "args": {k: v for k, v in part.function_call.args.items()}
                        })
                if tool_calls:
                    return AIMessage(content="", tool_calls=tool_calls)
                # Handle normal text response
                try:
                    return AIMessage(content=response.text)
                except ValueError:
                    # This case handles when response.text is not available
                    pass

            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = response.candidates[0].finish_reason.name
                if finish_reason != "STOP":
                    return AIMessage(content=f"Error: Gemini finished with reason: {finish_reason}")

            # Fallback for empty or unexpected responses
            return AIMessage(content="")

        except Exception as e:
            print(f"An error occurred while calling the Gemini API: {e}")
            return AIMessage(content=f"Error: Could not get a response from Gemini. Details: {e}")

class OllamaClient(BaseLLMClient):
    """LLM client for a local Ollama instance."""
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.api_url = f"{base_url}/api/chat"
        print(f"---INITIALIZED OLLAMA CLIENT (Model: {self.model}, URL: {self.api_url})---")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: print(f"---OLLAMA RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}---")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        payload = {
            "model": self.model,
            "messages": [{"role": msg.type, "content": msg.content} for msg in messages],
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        print(f"---CALLING OLLAMA API---")
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
        print(f"---INITIALIZED LM STUDIO CLIENT (URL: {self.api_url})---")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        before_sleep=lambda retry_state: print(f"---LM STUDIO RETRYING ({retry_state.attempt_number}/{retry_state.retry_object.stop.max_attempt_number}): {retry_state.outcome.exception()}---")
    )
    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None, temperature: Optional[float] = 0.7) -> AIMessage:
        payload = {
            "model": self.model,
            "messages": [{"role": msg.type, "content": msg.content} for msg in messages],
            "temperature": temperature,
        }
        print(f"---CALLING LM STUDIO API---")
        response = requests.post(self.api_url, json=payload)
        response.raise_for_status()
        response_data = response.json()

        content = response_data['choices'][0]['message']['content']
        return AIMessage(content=content)
