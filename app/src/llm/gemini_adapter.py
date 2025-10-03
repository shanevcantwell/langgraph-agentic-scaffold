# app/src/llm/gemini_adapter.py
import logging
import json
from typing import Dict, Optional, Any

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from tenacity import retry, stop_after_attempt, wait_exponential

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, SafetyFilterError, RateLimitError, ProxyError
from . import adapters_helpers

logger = logging.getLogger(__name__)

class GeminiAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], api_key: str, system_prompt: str):
        super().__init__(model_config)
        self._api_key = api_key
        genai.configure(api_key=api_key)
        # Initialize model WITHOUT system_instruction here, as we'll inject it into messages
        self.model = genai.GenerativeModel(
            self.config['api_identifier']
        )
        self.static_system_prompt = system_prompt # Store the static system prompt
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.model_name})")

    @property
    def api_base(self) -> Optional[str]:
        """Gemini does not use a custom base URL in this configuration."""
        return None

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "GeminiAdapter":
        """Creates a GeminiAdapter instance from the provider configuration."""
        if not provider_config.get("api_key"):
            raise ValueError(
                f"Cannot create GeminiAdapter for provider binding '{provider_config.get('binding_key')}': "
                "Missing 'api_key'. Please ensure the GOOGLE_API_KEY environment variable is set."
            )
        model_config = {
            "api_identifier": provider_config.get("api_identifier"),
            "parameters": provider_config.get("parameters", {}),
            "context_window": provider_config.get("context_window")
        }
        return cls(model_config=model_config,
                   api_key=provider_config["api_key"],
                   system_prompt=system_prompt)

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
            # which should never return a text response.
            if request.force_tool_call:
                logger.info("GeminiAdapter: Forcing a tool call using mode: ANY.")
                tool_config = {"function_calling_config": {"mode": "ANY"}}
            else:
                logger.info("GeminiAdapter: Allowing model to choose between tool call and text response.")
                tool_config = None
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
        
        except google_exceptions.RetryError as e:
            clean_message = ("A network error occurred, which is often due to a proxy blocking the request. "
                             "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted.")
            # Log the full error for debugging, but raise a clean message.
            logger.error(f"{clean_message} Original error: {e}", exc_info=True)
            # Re-raise as a specific, catchable error.
            raise ProxyError(clean_message) from e

        except Exception as e:
            # A generic catch-all for other proxy-related issues, like receiving an HTML error page.
            if "proxy" in str(e).lower() or "<html>" in str(e).lower():
                clean_message = ("A proxy error occurred, likely due to a blocked request. "
                                 "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted.")
                logger.error(f"{clean_message} Original error: {e}", exc_info=True)
                raise ProxyError(clean_message) from e

            logger.error(f"Gemini API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"Gemini API error: {e}") from e

    def _parse_and_format_response(self, request: StandardizedLLMRequest, response: Any) -> Dict[str, Any]:
        """
        Parses the raw response from the Gemini API and formats it into the
        standardized dictionary expected by the specialists. This includes
        handling safety filtering, JSON, tool calls, and text responses.
        """
        # Robustness check for safety filtering
        try:
            candidate = response.candidates[0]
        except (IndexError, AttributeError):
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

        # --- Response Parsing Logic ---
        # The order of checks is important: Tool Call -> JSON -> Text

        # 1. Check for a tool call response.
        if candidate.content.parts and hasattr(candidate.content.parts[0], 'function_call') and candidate.content.parts[0].function_call:
            part = candidate.content.parts[0] # type: ignore
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

        # 2. Check for a JSON response.
        if request.output_model_class:
            logger.info("GeminiAdapter returned JSON response.")
            content = response.text or "{}"
            try:
                json_response = json.loads(content)
                return {"json_response": self._post_process_json_response(json_response, request.output_model_class)} # Use the hook
            except json.JSONDecodeError as e:
                logger.warning(
                    f"GeminiAdapter direct JSON parse failed: {e}. Attempting robust extraction. Content: {content[:500]}..."
                )
                json_response = self._robustly_parse_json_from_text(content)
                if json_response:
                    return {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
                else:
                    logger.error("Failed to parse or extract JSON from the Gemini model's response.")
                    return {"text_response": content, "json_response": {}}

        # 3. Fallback to a standard text response.
        logger.info("GeminiAdapter returned text response.")
        return {"text_response": response.text}