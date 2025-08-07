# src/llm/clients.py

import os
import requests
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any

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

    def invoke(self, messages: List[BaseMessage]) -> AIMessage:
        # Note: Gemini has a specific format for message history.
        # This is a simplified conversion. A real implementation might need more robust mapping.
        gemini_messages = [
            {"role": "user" if isinstance(msg, HumanMessage) else "model", "parts": [msg.content]}
            for msg in messages if not isinstance(msg, SystemMessage)
        ]
        # Gemini API often uses the system prompt separately
        system_prompt = next((msg.content for msg in messages if isinstance(msg, SystemMessage)), None)
        
        # Placeholder for actual invocation logic
        print(f"---CALLING GEMINI API---")
        # response = self.model.generate_content(gemini_messages, generation_config={"temperature": 0.7})
        # return AIMessage(content=response.text)
        
        # Mock response for demonstration
        mock_response_content = f"Mock response from Gemini for prompt: '{messages[-1].content}'"
        return AIMessage(content=mock_response_content)

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

