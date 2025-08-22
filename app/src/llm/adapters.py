# app/src/llm/adapters.py
import logging
import json
import requests
from typing import Dict, Any, List, Optional, Type
import google.generativeai as genai
from pydantic import BaseModel
from langchain_core.messages import BaseMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError
from ..specialists.schemas import SystemPlan, WebContent

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120

class GeminiAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], api_key: str, system_prompt: str):
        super().__init__(model_config)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            self.config['api_identifier'],
            system_instruction=system_prompt
        )
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.config['api_identifier']})")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True # Re-raise the exception after the final attempt
    )
    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        messages = [{"role": "user" if m.type == 'human' else "model", "parts": [m.content]} for m in request.messages]
        generation_config = self.config.get('parameters', {}).copy()

        # Determine request type and configure API call parameters
        tools_to_pass = None
        if request.output_model_class:
            logger.info("GeminiAdapter: Invoking in JSON mode.")
            generation_config["response_mime_type"] = "application/json"
        elif request.tools:
            logger.info("GeminiAdapter: Invoking in Tool-calling mode.")
            tools_to_pass = request.tools
        else:
            logger.info("GeminiAdapter: Invoking in Text mode.")

        try:
            response = self.model.generate_content(
                messages,
                generation_config=generation_config,
                tools=tools_to_pass,
            )
            return self._parse_and_format_response(request, response)

        except Exception as e:
            logger.error(f"Gemini API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"Gemini API error: {e}") from e

    def _parse_and_format_response(self, request: StandardizedLLMRequest, response: Any) -> Dict[str, Any]:
        """
        Parses the raw response from the Gemini API and formats it into the
        standardized dictionary expected by the specialists. This includes
        handling safety filtering, JSON, tool calls, and text responses.
        """
        # Robustness check for safety filtering
        if not response.candidates:
            logger.warning("GeminiAdapter received a response with no candidates. This may be due to content filtering.")
            if request.output_model_class: return {"json_response": {}}
            if request.tools: return {"tool_calls": []}
            return {"text_response": "The model did not provide a response, possibly due to safety filters."}

        # If we requested JSON, we expect JSON.
        if request.output_model_class:
            logger.info("GeminiAdapter returned JSON response.")
            json_response = json.loads(response.text)
            return {"json_response": self._post_process_json_response(json_response, request.output_model_class)}

        # If we passed tools, check for a tool call.
        if request.tools:
            if response.candidates and response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'function_call'):
                part = response.candidates[0].content.parts[0]
                function_call = part.function_call
                args = {key: value for key, value in function_call.args.items()} if function_call.args else {}
                tool_call_id = f"call_{function_call.name}"
                tool_call_response = {
                    "tool_calls": [{"name": function_call.name, "args": args, "id": tool_call_id}]
                }
                logger.info(f"GeminiAdapter returned tool call: {tool_call_response}")
                return tool_call_response
            else:
                logger.info("GeminiAdapter was given tools but returned a text response.")
                return {"text_response": response.text}

        # Otherwise, it's a standard text response.
        logger.info("GeminiAdapter returned text response.")
        return {"text_response": response.text}

class LMStudioAdapter(BaseAdapter):
    # This adapter supports OpenAI-compatible APIs, such as LM Studio.
    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str):
        super().__init__(model_config)
        self.api_url = f"{base_url}/chat/completions"
        self.system_prompt = system_prompt
        logger.info(f"INITIALIZED LMStudioAdapter (Model: {self.config['api_identifier']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend([{"role": "user" if m.type == 'human' else "assistant", "content": m.content} for m in request.messages])

        payload = {
            "model": self.config['api_identifier'],
            "messages": messages,
            **self.config.get('parameters', {})
        }

        if self.config.get('supports_schema') and request.output_model_class:
            payload["response_format"] = {
                "type": "json_object",
                "schema": request.output_model_class.model_json_schema()
            }

        try:
            response = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']

            if self.config.get('supports_schema') and request.output_model_class:
                json_response = json.loads(content)
                return {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
            else:
                return {"text_response": content}
        except requests.RequestException as e:
            logger.error(f"LMStudio API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"LMStudio API error: {e}") from e

    def _post_process_json_response(self, json_response: Dict[str, Any], output_model_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
        return json_response
