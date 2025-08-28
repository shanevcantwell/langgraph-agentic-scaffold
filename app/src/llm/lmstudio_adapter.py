# app/src/llm/lmstudio_adapter.py
import logging
import html
import json
import os
import tiktoken
import re
from typing import Dict, Any, List, Optional, Type
from openai import OpenAI, RateLimitError as OpenAIRateLimitError, BadRequestError
from langchain_core.messages import BaseMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, RateLimitError
from . import adapters_helpers

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120

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
        if '/' in self.model_name or '\\' in self.model_name:
            logger.warning(
                f"The model name '{self.model_name}' contains path separators ('/' or '\\'). "
                "This can cause issues with some local model servers. Ensure this is the exact "
                "identifier expected by the server (often the model's filename)."
            )

        self.context_window = self.config.get('context_window') or 4096
        self.timeout = int(os.getenv("LMSTUDIO_TIMEOUT", REQUEST_TIMEOUT))
        self.temperature = self.config.get('parameters', {}).get('temperature', 0.7)
        self.max_tokens = self.config.get('parameters', {}).get('max_tokens') or 4096
        logger.info(f"INITIALIZED LMStudioAdapter. Requests will be sent to '{base_url}' for model "
                    f"'{self.model_name}' with a timeout of {self.timeout}s, max_tokens={self.max_tokens}, "
                    f"and context_window={self.context_window}. "
                    "Ensure this matches your LM Studio server setup."
                   )

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

    def _prune_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Proactively prunes the message history to fit within the model's context window.
        This implementation keeps the first message (original user prompt) and the most
        recent messages that fit within the token limit.
        """
        if not messages:
            return []

        try:
            # Using cl100k_base as a general-purpose tokenizer for OpenAI-compatible models.
            tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("tiktoken tokenizer 'cl100k_base' not found. Context pruning will be disabled.")
            return messages

        # Calculate the token count for each message and the system prompt
        message_tokens = [len(tokenizer.encode(msg.content or "")) for msg in messages]
        system_prompt_tokens = len(tokenizer.encode(self.system_prompt or ""))
        current_tokens = sum(message_tokens) + system_prompt_tokens

        if current_tokens <= self.context_window:
            return messages

        logger.warning(
            f"Total tokens ({current_tokens}) exceeds context window ({self.context_window}). Pruning message history."
        )

        # Reserve space for the output and a buffer.
        token_limit = self.context_window - self.max_tokens - (self.context_window // 10)

        # Pruning logic: keep the first message and the most recent N messages
        first_message = messages[0]
        first_message_token_count = message_tokens[0]
        
        final_tokens = system_prompt_tokens + first_message_token_count
        
        # Add recent messages from the end until we fill the context window
        temp_recent_messages = []
        for i in range(len(messages) - 1, 0, -1): # Iterate backwards, excluding the first message
            msg_token_count = message_tokens[i]
            if final_tokens + msg_token_count <= token_limit:
                final_tokens += msg_token_count
                temp_recent_messages.insert(0, messages[i]) # Prepend to keep order
            else:
                break # Stop when we run out of space

        pruned_messages = [first_message] + temp_recent_messages
        logger.info(
            f"Pruning complete. New token count: ~{final_tokens}. "
            f"Original message count: {len(messages)}, Pruned count: {len(pruned_messages)}"
        )
        return pruned_messages

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
        pruned_messages = self._prune_messages(request.messages)

        api_messages = adapters_helpers.format_openai_messages(
            messages=pruned_messages,
            static_system_prompt=self.system_prompt
        )

        # Dynamically build arguments to avoid sending null values,
        # which can cause issues with some servers.
        api_kwargs = {
            "model": self.model_name,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
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
                    logger.info("Forcing a tool call for the RouterSpecialist using tool_choice='required'.")
                    # While the OpenAI API allows forcing a specific tool by passing an object,
                    # many local model servers (like older versions of LM Studio) only support
                    # the string values "none", "auto", or "required". Using "required" is a
                    # more compatible way to ensure the router performs a tool call instead of
                    # generating conversational text.
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

            # If a tool call was forced (either by 'required' or by name) but not provided,
            # it's a failure. Return an empty list to signal this to the caller (e.g., the Router).
            tool_choice = api_kwargs.get("tool_choice")
            if tool_choice and tool_choice != "auto":
                logger.warning(f"LMStudioAdapter had tool_choice='{tool_choice}' but the model returned a text response instead of a tool call.")
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
        
        except BadRequestError as e:
            if "context length" in str(e).lower():
                error_message = (f"LMStudio API context length error: {e}. This can happen if the configured "
                                 f"'context_window' in config.yaml is too large for the loaded model.")
                logger.error(error_message, exc_info=True)
                raise LLMInvocationError(error_message) from e
            else:
                logger.error(f"LMStudio API BadRequestError: {e}", exc_info=True)
                raise LLMInvocationError(f"LMStudio API BadRequestError: {e}") from e

        except Exception as e:
            logger.error(f"LMStudio API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"LMStudio API error: {e}") from e

    def _post_process_json_response(self, json_response: Dict[str, Any], output_model_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
        # Some local models, when instructed to return JSON containing an HTML
        # document, will incorrectly HTML-escape the string content of the
        # 'html_document' field. This method corrects that by un-escaping it.
        if 'html_document' in json_response and isinstance(json_response.get('html_document'), str):
            logger.info("Found 'html_document' in response. Applying HTML un-escaping to its content.")
            json_response['html_document'] = html.unescape(json_response['html_document'])
        return json_response