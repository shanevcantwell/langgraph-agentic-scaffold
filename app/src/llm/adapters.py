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
        self.model = genai.GenerativeModel(self.config['api_identifier'], system_instruction=system_prompt)
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.config['api_identifier']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        try:
            response = self.model.generate_content(
                [m.content for m in request.messages],
                generation_config=self.config.get('parameters', {}),
                tools=request.tools if request.tools else None,
            )
            if response.candidates[0].content.parts[0].function_call:
                function_call = response.candidates[0].content.parts[0].function_call
                args = {key: value for key, value in function_call.args.items()}
                return {"next_specialist": args.get("next_specialist")}
            else:
                return response.text
        except Exception as e:
            raise LLMInvocationError(f"Gemini API error: {e}") from e

class LMStudioAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str):
        super().__init__(model_config)
        self.api_url = f"{base_url}/chat/completions"
        self.system_prompt = system_prompt
        logger.info(f"INITIALIZED LMStudioAdapter (Model: {self.config['api_identifier']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend([{"role": "user", "content": m.content} for m in request.messages])

        payload = {
            "model": self.config['api_identifier'],
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

            # Check if the content is a markdown code block for JSON
            if content.strip().startswith("```json") and content.strip().endswith("```"):
                # Extract the JSON string from the markdown code block
                json_string = content.strip()[len("```json"): -len("```")].strip()
            else:
                json_string = content.strip()

            if self.config.get('supports_schema') and request.output_schema:
                try:
                    return json.loads(json_string)
                except json.JSONDecodeError as e:
                    raise LLMInvocationError(f"LM Studio API error: Failed to parse JSON response with schema: {e}") from e
            else:
                return json_string
        except Exception as e:
            raise LLMInvocationError(f"LM Studio API error: {e}") from e