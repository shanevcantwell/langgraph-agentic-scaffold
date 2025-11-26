# app/src/llm/lmstudio_adapter.py
import logging
import json
import os
import tiktoken
from typing import Dict, Any, List, Optional, Type
from openai import OpenAI, RateLimitError as OpenAIRateLimitError, BadRequestError, APIConnectionError, PermissionDeniedError
import httpx
from langchain_core.messages import BaseMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from pydantic import BaseModel

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, RateLimitError, ProxyError
from . import adapters_helpers
import html

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
        self._base_url = base_url
        self._api_key = os.getenv("LMSTUDIO_API_KEY", "not-needed")
        self.client = OpenAI(base_url=self._base_url, api_key=self._api_key)
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
        # Pass through any additional sampling params (top_p, top_k, etc.) to the API
        self.extra_params = {k: v for k, v in self.config.get('parameters', {}).items()
                            if k not in ('temperature', 'max_tokens')}
        extra_params_str = f", extra_params={self.extra_params}" if self.extra_params else ""
        logger.info(f"INITIALIZED LMStudioAdapter. Requests will be sent to '{base_url}' for model "
                    f"'{self.model_name}' with a timeout of {self.timeout}s, max_tokens={self.max_tokens}, "
                    f"and context_window={self.context_window}{extra_params_str}. "
                    "Ensure this matches your LM Studio server setup."
                   )

    @property
    def api_base(self) -> Optional[str]:
        return self._base_url

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "LMStudioAdapter":
        """Creates an LMStudioAdapter instance from the provider configuration."""
        if not provider_config.get("base_url"):
            raise ValueError(
                f"Cannot create LMStudioAdapter for provider binding '{provider_config.get('binding_key')}': "
                "Missing 'base_url'. Please ensure the LMSTUDIO_BASE_URL environment variable is set."
            )
        model_config = {
            "api_identifier": provider_config.get("api_identifier"),
            "parameters": provider_config.get("parameters", {}),
            "context_window": provider_config.get("context_window")
        }
        return cls(model_config=model_config,
                   base_url=provider_config["base_url"],
                   system_prompt=system_prompt)

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

        # Handle Image Injection
        if request.image_data:
            # Find the last user message to attach the image to
            for i in range(len(pruned_messages) - 1, -1, -1):
                msg = pruned_messages[i]
                if msg.type == 'human':
                    logger.info("LMStudioAdapter: Injecting image into last user message.")
                    original_text = msg.content
                    # Construct multimodal content
                    new_content = [
                        {"type": "text", "text": original_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{request.image_data}"
                            }
                        }
                    ]
                    # Replace the message with a new HumanMessage containing the multimodal content
                    pruned_messages[i] = HumanMessage(content=new_content)
                    break

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
            **self.extra_params,  # top_p, top_k, etc. from config
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
                # If the request explicitly asks to force a tool call (e.g., for the router),
                # set the tool_choice to 'required'. This is a more robust and compatible
                # way to ensure a tool call than specifying a function name.
                if request.force_tool_call:
                    logger.info("Request has 'force_tool_call=True'. Setting tool_choice to 'required'.")
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
                    json_response = self._robustly_parse_json_from_text(content)

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
        
        # Consolidated proxy/network error handling. These exceptions all indicate a failure
        # to communicate with the server, often due to a proxy block or network issue.
        except (APIConnectionError, PermissionDeniedError, httpx.ProxyError) as e:
            clean_message = ("A network error occurred, which is often due to a proxy blocking the request. "
                             "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted.")
            # Log the full error for debugging, but raise a clean message.
            logger.error(f"{clean_message} Original error: {e}", exc_info=True)
            # Re-raise as a specific, catchable error.
            raise ProxyError(clean_message) from e

        except BadRequestError as e:
            if "context length" in str(e).lower():
                error_message = (f"LMStudio API context length error: {e}. This can happen if the configured "
                                 f"'context_window' in config.yaml is too large for the loaded model.")
                logger.error(error_message, exc_info=True)
                raise LLMInvocationError(error_message) from e
            # Check for HTML in the response body, which is a strong indicator of a proxy error page.
            else:
                logger.error(f"LMStudio API BadRequestError: {e}", exc_info=True)
                raise LLMInvocationError(f"LMStudio API BadRequestError: {e}") from e

        except Exception as e:
            logger.error(f"LMStudio API error during invoke: {e}", exc_info=True)
            raise LLMInvocationError(f"LMStudio API error: {e}") from e
