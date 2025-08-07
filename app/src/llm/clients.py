# src/llm/clients.py

import os
import requests
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# Using langchain_core.messages for consistency with the graph state
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage

class BaseLLMClient(ABC):
    """
    Abstract base class for all LLM clients, defining a standard interface
    for making API calls.
    """
    @abstractmethod
    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        """
        Sends a list of messages to the LLM and returns the response.

        Args:
            messages (List[BaseMessage]): A list of messages forming the conversation
                                          history and prompt.

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

    def invoke(self, messages: List[BaseMessage], tools: Optional[List[Any]] = None) -> AIMessage:
        # Note: Gemini has a specific format for message history.
        # This is a simplified conversion. A real implementation might need more robust mapping.
        gemini_messages = [
            {"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]}
            for msg in messages if not isinstance(msg, SystemMessage)
        ]
        # Gemini API often uses the system prompt separately
        system_prompt = next((msg.content for msg in messages if isinstance(msg, SystemMessage)), None)
        
        print(f"---CALLING GEMINI API---")

        # Gemini API prefers the system prompt to be set on the model at initialization.
        # As a workaround for handling it per-invocation, we prepend it to the first user message.
        if system_prompt and gemini_messages and gemini_messages[0]['role'] == 'user':
            original_content = gemini_messages[0]['parts'][0]
            gemini_messages[0]['parts'] = [system_prompt, original_content]

        try:
            # Prepare tools for Gemini
            gemini_tools = []
            if tools:
                for tool_obj in tools:
                    # Langchain tools have a .tool_name and .description attribute
                    # and a .args_schema for parameters
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
                generation_config={"temperature": 0.7},
                tools=gemini_tools if gemini_tools else None
            )
            
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
                else:
                    return AIMessage(content=response.text)
            elif response.prompt_feedback and response.prompt_feedback.block_reason:
                return AIMessage(content=f"Error: Gemini blocked the prompt due to: {response.prompt_feedback.block_reason.name}")
            elif response.candidates and response.candidates[0].finish_reason:
                return AIMessage(content=f"Error: Gemini finished with reason: {response.candidates[0].finish_reason.name}")
            else:
                return AIMessage(content="Error: Gemini returned an empty or unexpected response.")
        except Exception as e:
            print(f"An error occurred while calling the Gemini API: {e}")
            return AIMessage(content=f"Error: Could not get a response from Gemini. Details: {e}")

class OllamaClient(BaseLLMClient):
    """LLM client for a local Ollama instance."""
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.api_url = f"{base_url}/api/chat"
        print(f"---INITIALIZED OLLAMA CLIENT (Model: {self.model}, URL: {self.api_url})---")

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        payload = {
            "model": self.model,
            "messages": [{"role": msg.type, "content": msg.content} for msg in messages],
            "stream": False
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

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        payload = {
            "model": self.model,
            "messages": [{"role": msg.type, "content": msg.content} for msg in messages],
            "temperature": 0.7,
        }
        print(f"---CALLING LM STUDIO API---")
        response = requests.post(self.api_url, json=payload)
        response.raise_for_status()
        response_data = response.json()

        content = response_data['choices'][0]['message']['content']
        return AIMessage(content=content)

