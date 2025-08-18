import logging
import json
import requests
from typing import Dict, Any
import google.generativeai as genai

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120

class GeminiAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], api_key: str, system_prompt: str):
        super().__init__(model_config)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.config['model_name'], system_instruction=system_prompt)
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.config['model_name']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        # ... implementation to translate request to Gemini API call ...
        # This would use the schema enforcement feature we designed previously.
        pass # Placeholder for brevity

class LMStudioAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str):
        super().__init__(model_config)
        self.api_url = f"{base_url}/chat/completions"
        self.system_prompt = system_prompt
        logger.info(f"INITIALIZED LMStudioAdapter (Model: {self.config['model_name']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend([{"role": "user", "content": m.content} for m in request.messages])

        payload = {
            "model": self.config['model_name'],
            "messages": messages,
            **self.config.get('parameters', {}) # Apply all model-specific params from config
        }

        # Use schema enforcement if the model supports it and a schema is provided
        if self.config.get('supports_schema') and request.output_schema:
            payload["response_format"] = {
                "type": "json_object",
                "schema": request.output_schema
            }

        try:
            response = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            raise LLMInvocationError(f"LM Studio API error: {e}") from e
