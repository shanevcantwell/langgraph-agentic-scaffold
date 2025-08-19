import logging
import json
import requests
from typing import Dict, Any, List
import google.generativeai as genai
from langchain_core.messages import BaseMessage

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError

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

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        messages = [{"role": "user" if m.type == 'human' else "model", "parts": [m.content]} for m in request.messages]
        generation_config = self.config.get('parameters', {})

        try:
            if request.output_schema:
                logger.info("GeminiAdapter: Invoking in JSON mode and explicitly disabling tools.")
                generation_config["response_mime_type"] = "application/json"
                # In JSON mode, we MUST explicitly pass tools=None to override any
                # "sticky" tools from previous calls in the workflow.
                response = self.model.generate_content(
                    messages,
                    generation_config=generation_config,
                    tools=None
                )
            else:
                logger.info("GeminiAdapter: Invoking in Tool-calling or Text mode.")
                response = self.model.generate_content(
                    messages,
                    generation_config=generation_config,
                    tools=request.tools if request.tools else None,
                )

            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'function_call'):
                    function_call = part.function_call
                    args = {key: value for key, value in function_call.args.items()} if function_call.args else {}
                    tool_call_response = {
                        "tool_calls": [{
                            "name": function_call.name, "args": args, "id": "call_" + function_call.name
                        }]
                    }
                    logger.info(f"GeminiAdapter returned tool call: {tool_call_response}")
                    return tool_call_response

            if request.output_schema:
                logger.info("GeminiAdapter returned JSON response.")
                return {"json_response": json.loads(response.text)}
            else:
                logger.info("GeminiAdapter returned text response.")
                return {"text_response": response.text}

        except Exception as e:
            raise LLMInvocationError(f"Gemini API error: {e}") from e
                                                                        
class LMStudioAdapter(BaseAdapter):
    # This adapter's invoke method would need to be updated to support tool calling
    # For now, it remains as it was, supporting text and JSON schema output.
    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str):
        super().__init__(model_config)
        self.api_url = f"{base_url}/chat/completions"
        self.system_prompt = system_prompt
        logger.info(f"INITIALIZED LMStudioAdapter (Model: {self.config['api_identifier']})")

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        # Implementation remains the same as it doesn't support tool calling yet
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend([{"role": "user" if m.type == 'human' else "assistant", "content": m.content} for m in request.messages])

        payload = {
            "model": self.config['api_identifier'],
            "messages": messages,
            **self.config.get('parameters', {})
        }

        if self.config.get('supports_schema') and request.output_schema:
            payload["response_format"] = {"type": "json_object", "schema": request.output_schema}

        try:
            response = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            if self.config.get('supports_schema') and request.output_schema:
                return {"json_response": json.loads(content)}
            else:
                return {"text_response": content}
        except Exception as e:
            raise LLMInvocationError(f"LM Studio API error: {e}") from e