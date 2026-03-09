# app/src/llm/local_inference_adapter.py
"""Generic adapter for any OpenAI-compatible local inference server.

Speaks the standard /v1/chat/completions protocol. Works with llama-server,
LM Studio, vLLM, or any server exposing the OpenAI chat completions API.

Subclasses (e.g., LMStudioAdapter) can override hooks for server-specific
quirks without duplicating the core protocol logic.
"""
import logging
import json
import os
import time
import tiktoken
from uuid import uuid4
from typing import Dict, Any, List, Optional, Type
from openai import OpenAI, RateLimitError as OpenAIRateLimitError, BadRequestError, APIConnectionError, PermissionDeniedError, InternalServerError
import httpx
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, RateLimitError, ProxyError
from .tracing import capture_trace
import html

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120


class LocalInferenceAdapter(BaseAdapter):
    """
    Adapter for OpenAI-compatible local inference servers.

    Uses JSON schema enforcement via 'response_format' for tool-calling.
    Subclasses can override:
      - _preprocess_response_content() for response text cleanup
      - _resolve_schema_refs() for JSON schema $ref handling
      - _format_messages() for message formatting quirks
    """

    def __init__(self, model_config: Dict[str, Any], base_url: str, system_prompt: str, api_key: Optional[str] = None):
        super().__init__(model_config)
        if not base_url:
            raise ValueError(
                "LocalInferenceAdapter requires a 'base_url'. "
                "Please set the LOCAL_INFERENCE_BASE_URL (or LMSTUDIO_BASE_URL) environment variable in your .env file."
            )
        self._base_url = base_url
        self._api_key = api_key or os.getenv("LOCAL_INFERENCE_API_KEY") or os.getenv("LMSTUDIO_API_KEY", "not-needed")
        self.client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        self.system_prompt = system_prompt
        if '/' in self.model_name or '\\' in self.model_name:
            logger.warning(
                f"The model name '{self.model_name}' contains path separators ('/' or '\\'). "
                "This can cause issues with some local model servers. Ensure this is the exact "
                "identifier expected by the server (often the model's filename)."
            )

        # skip_schema_enforcement: skip response_format and parse JSON from free text
        self.skip_schema_enforcement = self.config.get('skip_schema_enforcement', False)

        self.context_window = self.config.get('context_window')  # None = let server handle limits
        self.timeout = int(
            os.getenv("LOCAL_INFERENCE_TIMEOUT")
            or os.getenv("LMSTUDIO_TIMEOUT", str(REQUEST_TIMEOUT))
        )
        # #159: Don't send defaults — let the server use per-model presets.
        # Only send parameters explicitly configured in user_settings.yaml.
        all_params = self.config.get('parameters') or {}
        self.temperature = all_params.get('temperature')
        self.max_tokens = all_params.get('max_tokens')
        self.max_image_size_bytes = self.config.get('max_image_size_mb', 10) * 1024 * 1024
        # Separate OpenAI-compatible params from non-standard ones
        HANDLED_PARAMS = {'temperature', 'max_tokens'}
        NON_STANDARD_PARAMS = {'top_k'}
        self.extra_params = {k: v for k, v in all_params.items()
                            if k not in HANDLED_PARAMS and k not in NON_STANDARD_PARAMS}
        self.extra_body = {k: v for k, v in all_params.items()
                          if k in NON_STANDARD_PARAMS}
        extra_params_str = f", extra_params={self.extra_params}" if self.extra_params else ""
        extra_body_str = f", extra_body={self.extra_body}" if self.extra_body else ""
        context_window_display = self.context_window if self.context_window else "unlimited (server native)"
        max_tokens_display = self.max_tokens if self.max_tokens else "server default"
        temp_display = self.temperature if self.temperature is not None else "server default"
        logger.info(f"INITIALIZED {self.__class__.__name__}. Requests will be sent to '{base_url}' for model "
                    f"'{self.model_name}' with a timeout of {self.timeout}s, temperature={temp_display}, "
                    f"max_tokens={max_tokens_display}, context_window={context_window_display}"
                    f"{extra_params_str}{extra_body_str}. "
                    "Unset params use server per-model presets."
                   )

    @property
    def api_base(self) -> Optional[str]:
        return self._base_url

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "LocalInferenceAdapter":
        """Creates a LocalInferenceAdapter instance from the provider configuration."""
        if not provider_config.get("base_url"):
            raise ValueError(
                f"Cannot create {cls.__name__} for provider binding '{provider_config.get('binding_key')}': "
                "Missing 'base_url'. Please ensure the LOCAL_INFERENCE_BASE_URL environment variable is set."
            )
        model_config = {
            "api_identifier": provider_config.get("api_identifier"),
            "parameters": provider_config.get("parameters", {}),
            "context_window": provider_config.get("context_window"),
            "skip_schema_enforcement": provider_config.get("skip_schema_enforcement", False),
        }
        return cls(model_config=model_config,
                   base_url=provider_config["base_url"],
                   system_prompt=system_prompt,
                   api_key=provider_config.get("api_key"))

    # --- Subclass hooks ---

    def _preprocess_response_content(self, content: str) -> str:
        """Hook for subclasses to preprocess response content before JSON parsing.

        Override in subclasses to strip server-specific control tokens.
        Base implementation returns content unchanged.
        """
        return content

    def _resolve_schema_refs(self, node: Any, defs: Dict[str, Any]) -> Any:
        """Hook for subclasses to resolve $ref pointers in JSON schemas.

        Some servers don't support JSON Schema $defs/$ref. Override to inline
        definitions. Base implementation returns the node unchanged (assumes
        the server handles $ref natively).
        """
        return node

    # --- Core methods ---

    @staticmethod
    def _get_known_params_for_tool(
        tool_name: str, tools: List[Type[BaseModel]]
    ) -> Optional[set]:
        """Look up valid parameter names for a tool from its Pydantic model.

        Used by _parse_completion to strip irrelevant params that the model
        may fill when JSON schema enforcement doesn't fully isolate per-tool fields.

        Returns None if tool not found (permissive fallback for unknown tools).
        """
        for tool in tools:
            if tool.__name__ == tool_name:
                return set(tool.model_fields.keys())
        return None

    def _build_tool_call_schema(self, tools: List[Type[BaseModel]]) -> Dict[str, Any]:
        """
        Build a draft-07 JSON schema for structured tool calling (#135).

        Uses oneOf to create per-tool action variants, each with only its own
        parameters. This prevents models from filling irrelevant fields.

        Args:
            tools: List of Pydantic model classes representing available tools

        Returns:
            JSON Schema dict for structured output
        """
        variants = []

        for tool in tools:
            schema = tool.model_json_schema()
            defs = schema.get("$defs", {})
            tool_required = schema.get("required", [])

            # Per-tool properties: tool_name (const) + only this tool's params
            tool_properties = {
                "tool_name": {"type": "string", "const": tool.__name__}
            }
            for prop_name, prop_def in schema.get("properties", {}).items():
                resolved = self._resolve_schema_refs(dict(prop_def), defs)
                if "description" not in resolved:
                    resolved["description"] = f"Parameter for {tool.__name__}"
                tool_properties[prop_name] = resolved

            variants.append({
                "type": "object",
                "required": ["tool_name"] + tool_required,
                "properties": tool_properties,
                "additionalProperties": False,
            })

        # Issue #138: Only add DONE for multi-tool (ReAct) scenarios.
        if len(tools) > 1:
            variants.append({
                "type": "object",
                "required": ["tool_name"],
                "properties": {
                    "tool_name": {"type": "string", "const": "DONE"}
                },
                "additionalProperties": False,
            })

        return {
            "title": "ToolCallResponse",
            "type": "object",
            "required": ["reasoning", "actions"],
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Your thought process before taking action"
                },
                "actions": {
                    "type": "array",
                    "items": {"oneOf": variants},
                    "minItems": 1,
                    "description": "One or more tool calls to execute. Use multiple items for independent operations."
                },
                "final_response": {
                    "type": "string",
                    "description": "Only when any action has tool_name DONE - the final summary"
                }
            }
        }

    def _prune_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Proactively prunes the message history to fit within the model's context window.
        Keeps the first message (original user prompt) and the most recent messages
        that fit within the token limit.

        If context_window is not configured (None), pruning is skipped entirely and
        the server's native limit handling is used instead.
        """
        if not messages:
            return []

        if self.context_window is None:
            return messages

        try:
            tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("tiktoken tokenizer 'cl100k_base' not found. Context pruning will be disabled.")
            return messages

        message_tokens = [len(tokenizer.encode(msg.content or "")) for msg in messages]
        system_prompt_tokens = len(tokenizer.encode(self.system_prompt or ""))
        current_tokens = sum(message_tokens) + system_prompt_tokens

        if current_tokens <= self.context_window:
            return messages

        logger.warning(
            f"Total tokens ({current_tokens}) exceeds context window ({self.context_window}). Pruning message history."
        )

        output_reserve = self.max_tokens if self.max_tokens else (self.context_window // 5)
        token_limit = self.context_window - output_reserve - (self.context_window // 10)

        first_message = messages[0]
        first_message_token_count = message_tokens[0]

        final_tokens = system_prompt_tokens + first_message_token_count

        temp_recent_messages = []
        for i in range(len(messages) - 1, 0, -1):
            msg_token_count = message_tokens[i]
            if final_tokens + msg_token_count <= token_limit:
                final_tokens += msg_token_count
                temp_recent_messages.insert(0, messages[i])
            else:
                break

        pruned_messages = [first_message] + temp_recent_messages
        logger.info(
            f"Pruning complete. New token count: ~{final_tokens}. "
            f"Original message count: {len(messages)}, Pruned count: {len(pruned_messages)}"
        )
        return pruned_messages

    def _format_messages(
        self,
        messages: List[BaseMessage],
        use_json_tool_format: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Format LangChain messages for OpenAI-compatible API.

        - Combines static and runtime system prompts into single system message
        - Converts tool_calls to OpenAI format: {id, type, function: {name, arguments}}

        Args:
            messages: LangChain messages to format
            use_json_tool_format: If True, append instruction to output JSON
        """
        # Collect all system instructions
        all_system_contents = [self.system_prompt] if self.system_prompt else []
        runtime_system_contents = [msg.content for msg in messages if msg.type == 'system']
        all_system_contents.extend(runtime_system_contents)

        # Issue #135: When using JSON schema fallback, instruct model to output JSON
        if use_json_tool_format:
            json_instruction = (
                "\n\n## CRITICAL: Output Format\n"
                "You MUST output your response as a single valid JSON object. "
                "Do NOT use <|channel|>, <|constrain|>, <|message|>, or any other special tokens. "
                "Do NOT use function calling syntax like 'to=functions.X'. "
                "Your ENTIRE response must be exactly this format:\n"
                '```json\n'
                '{"reasoning": "your thought process", "actions": [{"tool_name": "tool_name_here", ...params}]}\n'
                '```\n'
                "Start your response with '{' and end with '}'."
            )
            all_system_contents.append(json_instruction)

        final_system_content = "\n\n".join(filter(None, all_system_contents))

        api_messages = []
        if final_system_content:
            api_messages.append({"role": "system", "content": final_system_content})

        for msg in messages:
            if msg.type == 'system':
                continue  # Already processed
            elif msg.type == 'human':
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.type == 'ai':
                ai_msg_dict = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    # Convert LangChain format to OpenAI API format
                    ai_msg_dict["tool_calls"] = [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {})) if isinstance(tc.get("args"), dict) else str(tc.get("args", "{}"))
                            }
                        }
                        for i, tc in enumerate(msg.tool_calls)
                    ]
                api_messages.append(ai_msg_dict)
            elif msg.type == 'tool':
                api_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": str(msg.tool_call_id)
                })

        return api_messages

    def _build_request_kwargs(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """
        Build the OpenAI-compatible API request kwargs from a StandardizedLLMRequest.

        Handles message pruning, image injection, formatting,
        and response_format setup (JSON schema enforcement for tools and structured output).

        Returns a dict ready for client.chat.completions.create(**kwargs).
        """
        pruned_messages = self._prune_messages(request.messages)

        # Handle Image Injection
        if request.image_data:
            if not request.image_data.strip():
                raise ValueError("Image data is empty or whitespace-only")
            image_size = len(request.image_data)
            if image_size > self.max_image_size_bytes:
                raise ValueError(
                    f"Image data exceeds maximum size: {image_size / (1024*1024):.1f}MB > "
                    f"{self.max_image_size_bytes / (1024*1024):.0f}MB (configure max_image_size_mb in user_settings.yaml)"
                )
            for i in range(len(pruned_messages) - 1, -1, -1):
                msg = pruned_messages[i]
                if msg.type == 'human':
                    logger.info(f"{self.__class__.__name__}: Injecting image into last user message.")
                    original_text = msg.content
                    if not original_text or (isinstance(original_text, str) and not original_text.strip()):
                        raise ValueError("Cannot inject image into message with empty content.")
                    new_content = [
                        {"type": "text", "text": original_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{request.image_data}"
                            }
                        }
                    ]
                    pruned_messages[i] = HumanMessage(content=new_content)
                    break

        use_json_tool_format = bool(request.tools)
        api_messages = self._format_messages(pruned_messages, use_json_tool_format)

        # Dynamically build arguments to avoid sending null values.
        # Only send parameters that are explicitly configured.
        api_kwargs = {
            "model": self.model_name,
            "messages": api_messages,
            **self.extra_params,
        }
        if self.temperature is not None:
            api_kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            api_kwargs["max_tokens"] = self.max_tokens

        # JSON schema enforcement for tools (#135)
        if self.skip_schema_enforcement:
            logger.info(
                f"{self.__class__.__name__}: Schema enforcement skipped for '{self.model_name}' "
                "(skip_schema_enforcement=True). JSON will be parsed from text response."
            )
        elif request.tools:
            logger.info(f"{self.__class__.__name__}: Using JSON schema enforcement for tools (not native tool-calling).")
            tool_call_schema = self._build_tool_call_schema(request.tools)
            api_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ToolCallResponse",
                    "strict": True,
                    "schema": tool_call_schema,
                }
            }

        elif request.output_model_class and issubclass(request.output_model_class, BaseModel):
            schema_source = request.output_model_class
            logger.info(f"{self.__class__.__name__}: Invoking in JSON Schema enforcement mode with schema {schema_source.__name__}.")
            schema = schema_source.model_json_schema()
            # Inline $defs/$ref — llama-server can't resolve nested refs (llama.cpp #8073) (#260)
            defs = schema.pop("$defs", {})
            if defs:
                schema = self._resolve_schema_refs(schema, defs)
            api_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_source.__name__,
                    "strict": True,
                    "schema": schema,
                }
            }
        else:
            logger.info(f"{self.__class__.__name__}: Invoking in Text mode.")

        if self.extra_body:
            api_kwargs["extra_body"] = self.extra_body

        return api_kwargs

    def _parse_completion(self, completion, request: StandardizedLLMRequest, api_kwargs: Dict[str, Any], start_time: float) -> Dict[str, Any]:
        """
        Parse an OpenAI-compatible completion into the standardized response dict.

        Handles native tool calls, JSON schema-enforced tool calls, structured JSON output,
        and plain text responses. Captures trace with latency measurement.
        """
        if not completion.choices:
            raise LLMInvocationError(
                f"Server returned empty choices (model={api_kwargs.get('model', 'unknown')}). "
                "This usually means the server endpoint is wrong (missing /v1 prefix) "
                "or the model is not loaded."
            )
        message = completion.choices[0].message

        # --- Response Parsing ---
        # If the model responded with native tool calls, parse them.
        if message.tool_calls:
            logger.info(f"{self.__class__.__name__} received native tool calls: {message.tool_calls}")
            formatted_tool_calls = []
            for tool_call in message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                    formatted_tool_calls.append({"name": tool_call.function.name, "args": args, "id": tool_call.id})
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode tool call arguments: {tool_call.function.arguments}", exc_info=True)
            result = {"tool_calls": formatted_tool_calls}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # Parse tool call(s) from JSON-formatted response.
        if request.tools and ("response_format" in api_kwargs or self.skip_schema_enforcement):
            content = message.content or ""
            content = self._preprocess_response_content(content)
            if content.strip():
                try:
                    try:
                        json_resp = json.loads(content)
                    except json.JSONDecodeError:
                        json_resp = self._robustly_parse_json_from_text(content)
                        if not json_resp:
                            raise json.JSONDecodeError("No JSON found after preprocessing", content, 0)

                    # Primary path: "actions" array (concurrent dispatch)
                    actions = json_resp.get("actions", [])

                    # Fallback 1: singular "action" object (backward compat)
                    if not actions:
                        singular_action = json_resp.get("action")
                        if singular_action and isinstance(singular_action, dict):
                            logger.info(f"{self.__class__.__name__}: Falling back to singular 'action' format")
                            actions = [singular_action]

                    # Fallback 2: flat format {"tool_name": "...", ...} (no nesting)
                    if not actions:
                        flat_tool_name = json_resp.get("tool_name")
                        if flat_tool_name:
                            logger.info(f"{self.__class__.__name__}: Using flat format tool_name: {flat_tool_name}")
                            actions = [json_resp]

                    if actions:
                        # Check for DONE in any action — DONE takes priority
                        has_done = any(
                            a.get("tool_name") == "DONE" for a in actions
                            if isinstance(a, dict)
                        )

                        if has_done:
                            non_done = [a for a in actions if isinstance(a, dict) and a.get("tool_name") != "DONE"]
                            if non_done:
                                logger.warning(
                                    f"{self.__class__.__name__}: DONE mixed with {len(non_done)} other action(s). "
                                    f"DONE takes priority — discarding: {[a.get('tool_name') for a in non_done]}"
                                )
                            logger.info(f"{self.__class__.__name__}: JSON response indicates task DONE.")
                            result = {"text_response": json_resp.get("final_response", "")}
                            latency_ms = int((time.perf_counter() - start_time) * 1000)
                            capture_trace(request, result, latency_ms, self.model_name)
                            return result

                        # Build tool_calls list from all actions
                        tool_calls = []
                        for action in actions:
                            if not isinstance(action, dict):
                                logger.warning(f"{self.__class__.__name__}: Skipping non-dict action: {type(action)}")
                                continue
                            tool_name = action.get("tool_name")
                            if not tool_name:
                                logger.warning(f"{self.__class__.__name__}: Skipping action without tool_name: {list(action.keys())}")
                                continue

                            args = {k: v for k, v in action.items() if k != "tool_name" and v is not None}

                            # Defense-in-depth: strip params not belonging to this tool
                            if request.tools:
                                known = self._get_known_params_for_tool(tool_name, request.tools)
                                if known is not None:
                                    stripped = {k for k in args if k not in known}
                                    if stripped:
                                        logger.debug(f"{self.__class__.__name__}: Stripped irrelevant params from {tool_name}: {stripped}")
                                    args = {k: v for k, v in args.items() if k in known}

                            tool_calls.append({
                                "name": tool_name,
                                "args": args,
                                "id": f"json_{uuid4().hex[:8]}"
                            })

                        if tool_calls:
                            logger.info(f"{self.__class__.__name__}: Parsed {len(tool_calls)} tool call(s) from JSON: {[tc['name'] for tc in tool_calls]}")
                            result = {
                                "tool_calls": tool_calls,
                                "text_response": json_resp.get("reasoning", ""),
                            }
                            latency_ms = int((time.perf_counter() - start_time) * 1000)
                            capture_trace(request, result, latency_ms, self.model_name)
                            return result
                        else:
                            logger.warning(f"{self.__class__.__name__}: Actions present but no valid tool calls extracted")
                    else:
                        logger.warning(f"{self.__class__.__name__}: JSON parsed but no actions found. Keys: {list(json_resp.keys())}")
                except json.JSONDecodeError:
                    logger.warning(f"{self.__class__.__name__}: Failed to parse JSON response: {content[:200]}")

            # FALLTHROUGH GUARD - if we reach here in tools mode,
            # content was empty, JSON parse failed, or actions were missing.
            logger.warning(f"{self.__class__.__name__}: Tools mode fallthrough - content length: {len(content)}, first 100 chars: {content[:100]}")
            result = {"tool_calls": []}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # If a tool call was forced but not provided, signal failure.
        tool_choice = api_kwargs.get("tool_choice")
        if tool_choice and tool_choice != "auto":
            logger.warning(f"{self.__class__.__name__} had tool_choice='{tool_choice}' but the model returned a text response instead of a tool call.")
            result = {"tool_calls": []}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # If we requested a JSON schema, parse the content as JSON.
        if "response_format" in api_kwargs and api_kwargs["response_format"]["type"] == "json_schema":
            content = message.content
            if not content:
                reasoning_content = getattr(message, 'reasoning_content', None)
                if reasoning_content:
                    logger.info(f"{self.__class__.__name__}: Found structured output in reasoning_content (model-specific behavior)")
                    content = reasoning_content
                else:
                    content = "{}"
            content = self._preprocess_response_content(content)
            json_response = None
            try:
                json_response = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(
                    f"{self.__class__.__name__} received non-JSON text when JSON was expected. Attempting to extract JSON. Content: {content[:500]}..."
                )
                json_response = self._robustly_parse_json_from_text(content)

            if json_response:
                result = {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
            else:
                schema_name = request.output_model_class.__name__ if request.output_model_class else "unknown"
                error_msg = (
                    f"Model failed to produce valid {schema_name} structured output. "
                    f"Raw content: {content[:300]}..."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result
        else:
            # Standard text response
            content = message.content
            if not content:
                reasoning_content = getattr(message, 'reasoning_content', None)
                if reasoning_content:
                    logger.info(f"{self.__class__.__name__}: Found response in reasoning_content (model-specific behavior)")
                    content = reasoning_content
                else:
                    content = ""
            content = self._preprocess_response_content(content)
            json_data = self._robustly_parse_json_from_text(content)
            if json_data:
                result = {"json_response": json_data, "text_response": content}
            else:
                result = {"text_response": content}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

    def _call_with_error_handling(
        self,
        api_call,
        request: StandardizedLLMRequest,
        api_kwargs: Dict[str, Any],
        start_time: float,
        server_url: Optional[str] = None,
        on_connection_error=None,
        capture_errors: bool = True,
    ) -> Dict[str, Any]:
        """Execute an OpenAI API call with standardized error handling.

        Wraps the call in a try/except chain that maps OpenAI exceptions to
        LAS-specific error types. Shared by LocalInferenceAdapter.invoke() and
        PooledLocalInferenceAdapter.invoke() to avoid duplicating this logic.

        Args:
            api_call: Zero-arg callable that performs the API call and returns a completion.
            request: The original request (for trace capture).
            api_kwargs: The kwargs dict (for _parse_completion).
            start_time: perf_counter timestamp for latency measurement.
            server_url: If set, included in error messages for diagnostics.
            on_connection_error: Optional callback(e) invoked before raising on connection errors.
            capture_errors: If True, capture_trace on error paths (default True).
        """
        url_ctx = f" on {server_url}" if server_url else ""
        try:
            completion = api_call()
            return self._parse_completion(completion, request, api_kwargs, start_time)

        except OpenAIRateLimitError as e:
            error_message = f"API rate limit exceeded{url_ctx}: {e}"
            logger.error(error_message, exc_info=True)
            if capture_errors:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": error_message}, latency_ms, self.model_name)
            raise RateLimitError(error_message) from e

        except (APIConnectionError, PermissionDeniedError, httpx.ProxyError) as e:
            if on_connection_error:
                on_connection_error(e)
            clean_message = (
                f"A network error occurred{' connecting to ' + server_url if server_url else ''}, "
                "which is often due to a proxy blocking the request. "
                "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
            )
            logger.error(f"{clean_message} Original error: {e}", exc_info=True)
            if capture_errors:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
            raise ProxyError(clean_message) from e

        except BadRequestError as e:
            if "context length" in str(e).lower():
                error_message = (
                    f"API context length error{url_ctx}: {e}. This can happen if the configured "
                    "'context_window' in config.yaml is too large for the loaded model."
                )
                logger.error(error_message, exc_info=True)
                if capture_errors:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    capture_trace(request, {"error": error_message}, latency_ms, self.model_name)
                raise LLMInvocationError(error_message) from e
            else:
                logger.error(f"API BadRequestError{url_ctx}: {e}", exc_info=True)
                if capture_errors:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
                raise LLMInvocationError(f"API BadRequestError: {e}") from e

        except InternalServerError as e:
            # #255: Grammar parse errors (e.g. code-fenced JSON) return 500 with
            # the valid response embedded in the error body message. Try to recover.
            error_body = getattr(e, 'body', None)
            # OpenAI client unwraps the outer 'error' envelope — body is already
            # {'code': 500, 'message': '...', 'type': 'server_error'}
            if isinstance(error_body, dict):
                error_message = error_body.get('message', '') or error_body.get('error', {}).get('message', '')
            else:
                error_message = str(e)
            if "Failed to parse input" in error_message:
                recovered = self._robustly_parse_json_from_text(error_message)
                if recovered:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    logger.warning(
                        f"Recovered valid JSON from grammar parse error{url_ctx} "
                        f"(latency={latency_ms}ms). Server's grammar rejected code-fenced output."
                    )
                    result = {"json_response": self._post_process_json_response(recovered, request.output_model_class)}
                    if capture_errors:
                        capture_trace(request, result, latency_ms, self.model_name)
                    return result

            # Non-recoverable 500 — fall through to generic handler
            logger.error(f"API InternalServerError{url_ctx}: {e}", exc_info=True)
            if capture_errors:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
            raise LLMInvocationError(f"API error: {e}") from e

        except Exception as e:
            logger.error(f"API error{url_ctx}: {e}", exc_info=True)
            if capture_errors:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
            raise LLMInvocationError(f"API error: {e}") from e

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """
        Invokes the model via OpenAI-compatible chat completions API.
        """
        api_kwargs = self._build_request_kwargs(request)
        start_time = time.perf_counter()
        return self._call_with_error_handling(
            lambda: self.client.chat.completions.create(**api_kwargs, timeout=self.timeout),
            request, api_kwargs, start_time,
        )
