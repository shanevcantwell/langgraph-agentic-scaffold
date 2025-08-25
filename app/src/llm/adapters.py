# app/src/llm/adapters.py
import logging
import json
import os
import re
from typing import Dict, Any, List, Optional, Type
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
from langchain_core.messages import BaseMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, SafetyFilterError, RateLimitError
from . import adapters_helpers
from pydantic import BaseModel

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120

class GeminiAdapter(BaseAdapter):
    def __init__(self, model_config: Dict[str, Any], api_key: str, system_prompt: str):
        super().__init__(model_config)
        genai.configure(api_key=api_key)
        # Initialize model WITHOUT system_instruction here, as we'll inject it into messages
        self.model = genai.GenerativeModel(
            self.config['api_identifier']
        )
        self.static_system_prompt = system_prompt # Store the static system prompt
        logger.info(f"INITIALIZED GeminiAdapter (Model: {self.config['api_identifier']})")

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
            logger.info("GeminiAdapter: Forcing a tool call using tool_config.")
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
                # If the model fails to return valid JSON despite the request,
                # we handle it gracefully by treating it as a text response.
                logger.warning(
                    f"GeminiAdapter was asked for JSON but received non-JSON text. Content: {content}"
                )
                return {"text_response": content, "json_response": {}}

        # If we passed tools, check for a tool call.
        if request.tools:
            if response.candidates and response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'function_call'):
                part = response.candidates[0].content.parts[0]
                function_call = part.function_call

                # --- ADDED VALIDATION ---
                # Handle cases where the model hallucinates a tool call with no name.
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
                # Return an empty tool_calls list to conform to the expected output format for the Router.
                # The Router will see this and correctly identify it as an LLM failure.
                return {"tool_calls": []}

        # Otherwise, it's a standard text response.
        logger.info("GeminiAdapter returned text response.")
        return {"text_response": _get_safe_text(response)}

class LMStudioAdapter(BaseAdapter):
    """
    An adapter for OpenAI-compatible APIs, such as LM Studio.
    It supports full JSON schema enforcement via the 'tools' API, making it
    robust for specialists that require structured output.
    """
    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str):
        super().__init__(model_config)
        if not base_url:
            raise ValueError(
                "LMStudioAdapter requires a 'base_url'. "
                "Please set the LMSTUDIO_BASE_URL environment variable in your .env file."
            )
        self.client = OpenAI(base_url=base_url, api_key=os.getenv("LMSTUDIO_API_KEY", "not-needed"))
        self.system_prompt = system_prompt
        self.model_name = self.config.get('api_identifier', 'local-model')
        if '/' in self.model_name or '\\' in self.model_name:
            logger.warning(
                f"The model name '{self.model_name}' contains path separators ('/' or '\\'). "
                "This can cause issues with some local model servers. Ensure this is the exact "
                "identifier expected by the server (often the model's filename)."
            )

        self.timeout = int(os.getenv("LMSTUDIO_TIMEOUT", REQUEST_TIMEOUT))
        self.temperature = self.config.get('parameters', {}).get('temperature', 0.7)
        logger.info(f"INITIALIZED LMStudioAdapter. Requests will be sent to '{base_url}' for model "
                    f"'{self.model_name}' with a timeout of {self.timeout} seconds. "
                    "Ensure this matches your LM Studio server setup.")

    def _extract_json_from_response(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Tries to extract a JSON object from a string that might contain extraneous text
        or be wrapped in markdown code blocks.
        """
        if not isinstance(text, str):
            return None

        # Pattern to find JSON within markdown code blocks (```json ... ```)
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("Found a JSON code block, but failed to parse it.")
                pass

        # Fallback to finding the first '{' and last '}'
        try:
            start_index = text.find('{')
            end_index = text.rfind('}')
            if start_index != -1 and end_index != -1 and end_index > start_index:
                json_str = text[start_index:end_index+1]
                return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            pass

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """
        Invokes the model, dynamically using the 'response_format' parameter
        to enforce a JSON schema if a Pydantic model is provided in the request,
        as per LM Studio's documentation.
        """
        api_messages = adapters_helpers.format_openai_messages(
            messages=request.messages,
            static_system_prompt=self.system_prompt
        )

        # Dynamically build arguments to avoid sending null values,
        # which can cause issues with some servers.
        api_kwargs = {
            "model": self.model_name,
            "messages": api_messages,
            "temperature": self.temperature,
        }

        # --- Intent Detection: Prioritize native tool-calling ---
        # If the request includes tools, use the native tool-calling API.
        # This is the modern, preferred method for routing and actions.
        if request.tools:
            logger.info("LMStudioAdapter: Invoking in native Tool-calling mode.")
            tool_names = []
            tools_to_pass = []
            for tool in request.tools:
                if issubclass(tool, BaseModel):
                    tool_name = tool.__name__
                    tool_names.append(tool_name)
                    tools_to_pass.append({
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": tool.__doc__ or f"Schema for {tool.__name__}",
                            "parameters": tool.model_json_schema()
                        }
                    })
            if tools_to_pass:
                api_kwargs["tools"] = tools_to_pass
                # The RouterSpecialist's only job is to route. It should always be
                # forced to use its 'Route' tool. This prevents it from generating
                # conversational text, which it is not designed to handle.
                if len(tool_names) == 1 and tool_names[0] == 'Route':
                    logger.info("Forcing a tool choice for the RouterSpecialist.")
                    # Using "required" is a more general way to force a tool call and may be
                    # more compatible with different OpenAI-compatible servers than specifying
                    # the tool by name. Since the router only has one tool, this is equivalent.
                    api_kwargs["tool_choice"] = "required"
                else:
                    api_kwargs["tool_choice"] = "auto"

        # If no tools are present, but a specific output model is requested,
        # use the JSON schema enforcement mode.
        elif request.output_model_class and issubclass(request.output_model_class, BaseModel):
            schema_source = request.output_model_class
            logger.info(f"LMStudioAdapter: Invoking in JSON Schema enforcement mode with schema {schema_source.__name__}.")
            api_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_source.__name__,
                    "strict": True,
                    "schema": schema_source.model_json_schema(),
                }
            }
        # Otherwise, invoke in standard text generation mode.
        else:
            logger.info("LMStudioAdapter: Invoking in Text mode.")

        try:
            completion = self.client.chat.completions.create(**api_kwargs, timeout=self.timeout)
            message = completion.choices[0].message

            # --- Response Parsing ---
            # If the model responded with tool calls, parse them.
            if message.tool_calls:
                logger.info(f"LMStudioAdapter received native tool calls: {message.tool_calls}")
                formatted_tool_calls = []
                for tool_call in message.tool_calls:
                    try:
                        # The 'arguments' field from the API is a JSON string that needs to be parsed.
                        args = json.loads(tool_call.function.arguments)
                        formatted_tool_calls.append({"name": tool_call.function.name, "args": args, "id": tool_call.id})
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode tool call arguments: {tool_call.function.arguments}", exc_info=True)
                return {"tool_calls": formatted_tool_calls}

            # If a tool call was required but not provided, return an empty list.
            # This signals a failure to the RouterSpecialist.
            if api_kwargs.get("tool_choice") == "required":
                logger.warning("LMStudioAdapter had tool_choice='required' but the model returned a text response.")
                return {"tool_calls": []}

            # If we requested a JSON schema, parse the content as JSON.
            if "response_format" in api_kwargs and api_kwargs["response_format"]["type"] == "json_schema":
                content = message.content or "{}"
                json_response = None
                try:
                    # First, try to parse directly
                    json_response = json.loads(content)
                except json.JSONDecodeError:
                    # If direct parsing fails, try to extract from a potentially messy string
                    logger.warning(
                        f"LMStudioAdapter received non-JSON text when JSON was expected. Attempting to extract JSON. Content: {content[:500]}..."
                    )
                    json_response = self._extract_json_from_response(content)

                if json_response:
                    return {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
                else:
                    # If extraction also fails, log the failure and return as text.
                    logger.error(
                        f"Failed to parse or extract JSON from the model's response."
                    )
                    return {"text_response": content, "json_response": {}}
            else:
                # Standard text response.
                return {"text_response": message.content or ""}
        
        except OpenAIRateLimitError as e:
            error_message = f"LMStudio API rate limit exceeded: {e}"
            logger.error(error_message, exc_info=True)
            raise RateLimitError(error_message) from e

        except Exception as e:
            logger.error(f"LMStudio API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"LMStudio API error: {e}") from e

    def _post_process_json_response(self, json_response: Dict[str, Any], output_model_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
        return json_response
