# app/src/llm/gemini_adapter.py
import logging
import json
from typing import Dict, Any

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from tenacity import retry, stop_after_attempt, wait_exponential

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, SafetyFilterError, RateLimitError
from . import adapters_helpers

logger = logging.getLogger(__name__)

class GeminiAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], api_key: str, system_prompt: str):
        super().__init__(model_config)
        genai.configure(api_key=api_key)
        # Initialize model WITHOUT system_instruction here, as we'll inject it into messages
        self.model = genai.GenerativeModel(
            self.config['api_identifier']
        )
        self.static_system_prompt = system_prompt # Store the static system prompt
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.model_name})")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True # Re-raise the exception after the final attempt
    )
    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        gemini_api_messages = adapters_helpers.format_gemini_messages(
            messages=request.messages,
            static_system_prompt=self.static_system_prompt
        )

        generation_config = self.config.get('parameters', {}).copy()

        # Initialize API call parameters
        tools_to_pass = None
        tool_config = None

        # Determine request type and configure API call parameters
        if request.output_model_class:
            logger.info("GeminiAdapter: Invoking in JSON mode.")
            generation_config["response_mime_type"] = "application/json"
        elif request.tools:
            logger.info("GeminiAdapter: Invoking in Tool-calling mode.")
            tools_to_pass = request.tools
            # Force the model to call a tool. This is critical for the router,
            # which should never return a text response. This is the Gemini
            # equivalent of OpenAI's `tool_choice="required"`.
            tool_config = {"function_calling_config": {"mode": "ANY"}}

            # --- Add special handling for the Router ---
            # If the only tool is 'Route', we can be more specific to ensure
            # the model makes a routing decision. This is a more robust way to
            # force a tool call than just using mode: "ANY".
            if len(request.tools) == 1 and hasattr(request.tools[0], '__name__') and request.tools[0].__name__ == 'Route':
                logger.info("GeminiAdapter: Forcing a 'Route' tool call for the RouterSpecialist by specifying allowed_function_names.")
                tool_config["function_calling_config"]["allowed_function_names"] = ["Route"]
            else:
                logger.info("GeminiAdapter: Forcing a tool call using generic tool_config.")
        else:
            logger.info("GeminiAdapter: Invoking in Text mode.")

        try:
            response = self.model.generate_content(
                gemini_api_messages, # Use the prepared messages
                generation_config=generation_config,
                tools=tools_to_pass,
                tool_config=tool_config,
            )
            return self._parse_and_format_response(request, response)

        # Be specific about the exceptions we can handle gracefully.
        except google_exceptions.ResourceExhausted as e:
            error_message = f"Gemini API rate limit exceeded: {e}"
            logger.error(error_message, exc_info=True)
            raise RateLimitError(error_message) from e

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
            # First, check for a documented safety block. This is the most likely reason for an empty response.
            if hasattr(response, 'prompt_feedback') and getattr(response.prompt_feedback, 'block_reason', None):
                block_reason = response.prompt_feedback.block_reason
                ratings = response.prompt_feedback.safety_ratings
                error_message = (f"Gemini response blocked due to safety filters. "
                                 f"Reason: {block_reason}. Ratings: {ratings}")
                logger.error(error_message)
                raise SafetyFilterError(error_message)
            else:
                # If there are no candidates and no documented block reason, it's a different, more generic API issue.
                error_message = "Gemini API returned an empty response with no candidates and no specific safety block reason. This could be a transient API issue."
                logger.error(f"{error_message} Full response object: {response}")
                raise LLMInvocationError(error_message)

        # Helper to safely access response.text, which can fail if the model
        # returns a tool call or other non-text part.
        def _get_safe_text(response_obj: Any) -> str:
            try:
                return response_obj.text
            except ValueError:
                logger.warning(
                    "response.text accessor failed. This can happen if the model returns a tool call "
                    "or empty content. Returning empty string."
                )
                return ""

        # If we requested JSON, we expect JSON.
        if request.output_model_class:
            logger.info("GeminiAdapter returned JSON response.")
            content = _get_safe_text(response) or "{}"
            try:
                json_response = json.loads(content)
                return {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
            except json.JSONDecodeError:
                logger.warning(
                    f"GeminiAdapter was asked for JSON but received non-JSON text. Content: {content}"
                )
                return {"text_response": content, "json_response": {}}

        # If we passed tools, check for a tool call.
        if request.tools:
            if response.candidates and response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'function_call'):
                part = response.candidates[0].content.parts[0]
                function_call = part.function_call

                if not function_call.name:
                    logger.warning("GeminiAdapter received a tool call with an empty name. Treating as a failed tool call.")
                    return {"tool_calls": []}

                args = {key: value for key, value in function_call.args.items()} if function_call.args else {}
                tool_call_id = f"call_{function_call.name}"
                tool_call_response = {
                    "tool_calls": [{"name": function_call.name, "args": args, "id": tool_call_id}]
                }
                logger.info(f"GeminiAdapter returned tool call: {tool_call_response}")
                return tool_call_response
            else:
                logger.warning("GeminiAdapter was given tools but returned a text response instead of a tool call.")
                return {"tool_calls": []}

        # Otherwise, it's a standard text response.
        logger.info("GeminiAdapter returned text response.")
        return {"text_response": _get_safe_text(response)}