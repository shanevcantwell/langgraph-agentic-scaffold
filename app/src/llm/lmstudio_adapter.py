# app/src/llm/lmstudio_adapter.py
import logging
import json
import os
import time
import tiktoken
from uuid import uuid4
from typing import Dict, Any, List, Optional, Type
from openai import OpenAI, RateLimitError as OpenAIRateLimitError, BadRequestError, APIConnectionError, PermissionDeniedError
import httpx
from langchain_core.messages import BaseMessage, HumanMessage
# tenacity removed: LMStudio is local and won't rate-limit; retry logic was dead code
from pydantic import BaseModel

from .adapter import BaseAdapter, StandardizedLLMRequest, LLMInvocationError, RateLimitError, ProxyError
from .tracing import capture_trace
import html

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 120

class LMStudioAdapter(BaseAdapter):
    """
    An adapter for OpenAI-compatible APIs, such as LM Studio.
    Uses JSON schema enforcement via 'response_format' for tool-calling instead
    of native Harmony format, which degrades after ~10 calls with some models.
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

        self.context_window = self.config.get('context_window')  # None if not configured; let LMStudio handle limits
        self.timeout = int(os.getenv("LMSTUDIO_TIMEOUT", REQUEST_TIMEOUT))
        self.temperature = self.config.get('parameters', {}).get('temperature', 0.7)
        self.max_tokens = self.config.get('parameters', {}).get('max_tokens') or 4096
        self.max_image_size_bytes = self.config.get('max_image_size_mb', 10) * 1024 * 1024
        # Separate OpenAI-compatible params from non-standard ones
        # OpenAI SDK supports: top_p, frequency_penalty, presence_penalty, etc.
        # Non-standard params (like top_k) go via extra_body for LM Studio
        HANDLED_PARAMS = {'temperature', 'max_tokens'}
        NON_STANDARD_PARAMS = {'top_k'}  # LM Studio supports these, but OpenAI SDK doesn't

        all_params = self.config.get('parameters', {})
        self.extra_params = {k: v for k, v in all_params.items()
                            if k not in HANDLED_PARAMS and k not in NON_STANDARD_PARAMS}
        self.extra_body = {k: v for k, v in all_params.items()
                          if k in NON_STANDARD_PARAMS}
        extra_params_str = f", extra_params={self.extra_params}" if self.extra_params else ""
        extra_body_str = f", extra_body={self.extra_body}" if self.extra_body else ""
        context_window_display = self.context_window if self.context_window else "unlimited (LMStudio native)"
        logger.info(f"INITIALIZED LMStudioAdapter. Requests will be sent to '{base_url}' for model "
                    f"'{self.model_name}' with a timeout of {self.timeout}s, max_tokens={self.max_tokens}, "
                    f"and context_window={context_window_display}{extra_params_str}{extra_body_str}. "
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

    @staticmethod
    def _resolve_schema_refs(node: Any, defs: Dict[str, Any]) -> Any:
        """Recursively resolve $ref pointers by inlining definitions from $defs.

        LM Studio's structured output engine doesn't support JSON Schema $defs/$ref.
        Pydantic v2 generates $defs for nested model types (e.g., List[ParallelCall]).
        This method walks a schema node and replaces every $ref with the actual
        definition, producing a flat schema LM Studio can enforce.
        """
        if isinstance(node, dict):
            # Node is a $ref — replace with the referenced definition
            if "$ref" in node and len(node) == 1:
                ref_path = node["$ref"]  # e.g. "#/$defs/ParallelCall"
                ref_name = ref_path.split("/")[-1]
                if ref_name not in defs:
                    return node  # Unknown ref — leave as-is
                resolved = defs[ref_name]
                # Recursively resolve in case the definition itself has $refs
                return LMStudioAdapter._resolve_schema_refs(dict(resolved), defs)

            # Otherwise recurse into each value
            return {k: LMStudioAdapter._resolve_schema_refs(v, defs) for k, v in node.items()}

        if isinstance(node, list):
            return [LMStudioAdapter._resolve_schema_refs(item, defs) for item in node]

        return node

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
        parameters. This prevents models from filling irrelevant fields (e.g.,
        putting a `command` arg on a `create_directory` call).

        This schema is used instead of native tool-calling (Harmony) because
        models like gpt-oss-20b degrade after ~10 tool calls, emitting garbled
        Harmony tokens. JSON schema enforcement via response_format provides
        logit masking that keeps the model on-schema throughout the ReAct loop.

        Args:
            tools: List of Pydantic model classes representing available tools

        Returns:
            JSON Schema dict with $schema declaration (required by LMStudio)
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
            "$schema": "http://json-schema.org/draft-07/schema#",
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
        This implementation keeps the first message (original user prompt) and the most
        recent messages that fit within the token limit.

        If context_window is not configured (None), pruning is skipped entirely and
        LMStudio's native per-model "Stop at Limit" handling is used instead.
        """
        if not messages:
            return []

        # Skip pruning if no context_window configured - let LMStudio handle limits natively
        if self.context_window is None:
            return messages

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

    def _format_lmstudio_messages(
        self,
        messages: List[BaseMessage],
        use_json_tool_format: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Format LangChain messages for LMStudio API.

        Issue #89: LMStudio-specific formatting, not shared with OpenAI adapter.
        - Combines static and runtime system prompts into single system message
        - Converts tool_calls to OpenAI format: {id, type, function: {name, arguments}}
        - Uses content: "" (not null) when tool_calls present (LMStudio requirement)

        Args:
            messages: LangChain messages to format
            use_json_tool_format: If True, append instruction to output JSON instead of Harmony
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
                    # LMStudio requires content to be string, not null
                    ai_msg_dict["content"] = ""
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

        Handles message pruning, image injection, LMStudio-specific formatting,
        and response_format setup (JSON schema enforcement for tools and structured output).

        Returns a dict ready for client.chat.completions.create(**kwargs).
        """
        pruned_messages = self._prune_messages(request.messages)

        # Handle Image Injection
        if request.image_data:
            # Invariant: reject empty/whitespace-only image data (e.g., 0-byte file upload)
            if not request.image_data.strip():
                raise ValueError("Image data is empty or whitespace-only")
            # Invariant: reject oversized images (would exceed context window)
            image_size = len(request.image_data)
            if image_size > self.max_image_size_bytes:
                raise ValueError(
                    f"Image data exceeds maximum size: {image_size / (1024*1024):.1f}MB > "
                    f"{self.max_image_size_bytes / (1024*1024):.0f}MB (configure max_image_size_mb in user_settings.yaml)"
                )
            # Find the last user message to attach the image to
            for i in range(len(pruned_messages) - 1, -1, -1):
                msg = pruned_messages[i]
                if msg.type == 'human':
                    logger.info("LMStudioAdapter: Injecting image into last user message.")
                    original_text = msg.content
                    # Invariant: multimodal text field must be non-empty (LM Studio rejects empty)
                    if not original_text or (isinstance(original_text, str) and not original_text.strip()):
                        raise ValueError("Cannot inject image into message with empty content.")
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

        # Issue #89: Use LMStudio-specific formatting (not shared OpenAI helper)
        # Issue #135: If tools present, add JSON format instruction to discourage Harmony
        use_json_tool_format = bool(request.tools)
        api_messages = self._format_lmstudio_messages(pruned_messages, use_json_tool_format)

        # Dynamically build arguments to avoid sending null values,
        # which can cause issues with some servers.
        api_kwargs = {
            "model": self.model_name,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **self.extra_params,  # top_p, top_k, etc. from config
        }

        # --- Intent Detection: JSON schema enforcement for tools (#135) ---
        # Instead of native tool-calling (Harmony), use response_format with JSON schema.
        # This is more reliable for models like gpt-oss that degrade after ~10 tool calls.
        if request.tools:
            logger.info("LMStudioAdapter: Using JSON schema enforcement for tools (not native tool-calling).")
            tool_call_schema = self._build_tool_call_schema(request.tools)
            api_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ToolCallResponse",
                    "strict": True,
                    "schema": tool_call_schema,
                }
            }
            # NOTE: We intentionally do NOT pass api_kwargs["tools"] - schema enforcement only

        # If no tools are present, but a specific output model is requested,
        # use the JSON schema enforcement mode.
        elif request.output_model_class and issubclass(request.output_model_class, BaseModel):
            schema_source = request.output_model_class
            logger.info(f"LMStudioAdapter: Invoking in JSON Schema enforcement mode with schema {schema_source.__name__}.")
            # Issue #135: Add $schema declaration required by LMStudio
            schema = schema_source.model_json_schema()
            schema["$schema"] = "http://json-schema.org/draft-07/schema#"
            api_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_source.__name__,
                    "strict": True,
                    "schema": schema,
                }
            }
        # Otherwise, invoke in standard text generation mode.
        else:
            logger.info("LMStudioAdapter: Invoking in Text mode.")

        # Pass non-standard params (like top_k) via extra_body for LM Studio
        if self.extra_body:
            api_kwargs["extra_body"] = self.extra_body

        return api_kwargs

    def _parse_completion(self, completion, request: StandardizedLLMRequest, api_kwargs: Dict[str, Any], start_time: float) -> Dict[str, Any]:
        """
        Parse an OpenAI-compatible completion into the standardized response dict.

        Handles native tool calls, JSON schema-enforced tool calls, structured JSON output,
        and plain text responses. Captures trace with latency measurement.

        Args:
            completion: The OpenAI completion response object
            request: The original request (for checking tools, output_model_class)
            api_kwargs: The kwargs used for the request (for checking response_format, tool_choice)
            start_time: perf_counter timestamp from before the HTTP call (for latency)
        """
        if not completion.choices:
            raise LLMInvocationError(
                f"LMStudio returned empty choices (model={api_kwargs.get('model', 'unknown')}). "
                "This usually means the server endpoint is wrong (missing /v1 prefix) "
                "or the model is not loaded."
            )
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
            result = {"tool_calls": formatted_tool_calls}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # Issue #135: Parse tool call(s) from JSON schema-enforced response.
        # This is the primary path when request.tools is set - we use response_format
        # with JSON schema instead of native tool-calling (Harmony) for reliability.
        # Phase 0.9: Supports "actions" array for concurrent multi-tool dispatch.
        if request.tools and "response_format" in api_kwargs:
            content = message.content or ""
            if content.strip():
                try:
                    json_resp = json.loads(content)

                    # Primary path: "actions" array (Phase 0.9 concurrent dispatch)
                    actions = json_resp.get("actions", [])

                    # Fallback 1: singular "action" object (backward compat)
                    if not actions:
                        singular_action = json_resp.get("action")
                        if singular_action and isinstance(singular_action, dict):
                            logger.info("LMStudioAdapter: Falling back to singular 'action' format")
                            actions = [singular_action]

                    # Fallback 2: flat format {"tool_name": "...", ...} (no nesting)
                    if not actions:
                        flat_tool_name = json_resp.get("tool_name")
                        if flat_tool_name:
                            logger.info(f"LMStudioAdapter: Using flat format tool_name: {flat_tool_name}")
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
                                    f"LMStudioAdapter: DONE mixed with {len(non_done)} other action(s). "
                                    f"DONE takes priority — discarding: {[a.get('tool_name') for a in non_done]}"
                                )
                            logger.info("LMStudioAdapter: JSON response indicates task DONE.")
                            result = {"text_response": json_resp.get("final_response", "")}
                            latency_ms = int((time.perf_counter() - start_time) * 1000)
                            capture_trace(request, result, latency_ms, self.model_name)
                            return result

                        # Build tool_calls list from all actions
                        tool_calls = []
                        for action in actions:
                            if not isinstance(action, dict):
                                logger.warning(f"LMStudioAdapter: Skipping non-dict action: {type(action)}")
                                continue
                            tool_name = action.get("tool_name")
                            if not tool_name:
                                logger.warning(f"LMStudioAdapter: Skipping action without tool_name: {list(action.keys())}")
                                continue

                            # Extract args (everything except tool_name, skip None values)
                            args = {k: v for k, v in action.items() if k != "tool_name" and v is not None}

                            # Defense-in-depth: strip params not belonging to this tool
                            if request.tools:
                                known = self._get_known_params_for_tool(tool_name, request.tools)
                                if known is not None:
                                    stripped = {k for k in args if k not in known}
                                    if stripped:
                                        logger.debug(f"LMStudioAdapter: Stripped irrelevant params from {tool_name}: {stripped}")
                                    args = {k: v for k, v in args.items() if k in known}

                            tool_calls.append({
                                "name": tool_name,
                                "args": args,
                                "id": f"json_{uuid4().hex[:8]}"
                            })

                        if tool_calls:
                            logger.info(f"LMStudioAdapter: Parsed {len(tool_calls)} tool call(s) from JSON: {[tc['name'] for tc in tool_calls]}")
                            # Thread reasoning through so ReActMixin can capture it as thought
                            result = {
                                "tool_calls": tool_calls,
                                "text_response": json_resp.get("reasoning", ""),
                            }
                            latency_ms = int((time.perf_counter() - start_time) * 1000)
                            capture_trace(request, result, latency_ms, self.model_name)
                            return result
                        else:
                            logger.warning("LMStudioAdapter: Actions present but no valid tool calls extracted")
                    else:
                        logger.warning(f"LMStudioAdapter: JSON parsed but no actions found. Keys: {list(json_resp.keys())}")
                except json.JSONDecodeError:
                    logger.warning(f"LMStudioAdapter: Failed to parse JSON response: {content[:200]}")

            # Issue #136: FALLTHROUGH GUARD - if we reach here in tools mode,
            # content was empty, JSON parse failed, or actions were missing.
            # Return empty tool_calls to signal failure - do NOT fall through
            # to output_model_class path which would raise ValueError.
            logger.warning(f"LMStudioAdapter: Tools mode fallthrough - content length: {len(content)}, first 100 chars: {content[:100]}")
            result = {"tool_calls": []}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # If a tool call was forced (either by 'required' or by name) but not provided,
        # it's a failure. Return an empty list to signal this to the caller (e.g., the Router).
        tool_choice = api_kwargs.get("tool_choice")
        if tool_choice and tool_choice != "auto":
            logger.warning(f"LMStudioAdapter had tool_choice='{tool_choice}' but the model returned a text response instead of a tool call.")
            result = {"tool_calls": []}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

        # If we requested a JSON schema, parse the content as JSON.
        if "response_format" in api_kwargs and api_kwargs["response_format"]["type"] == "json_schema":
            # Issue #127: Some models (e.g., nemotron) put structured output in
            # reasoning_content instead of content. Check both fields.
            content = message.content
            if not content:
                reasoning_content = getattr(message, 'reasoning_content', None)
                if reasoning_content:
                    logger.info("LMStudioAdapter: Found structured output in reasoning_content (model-specific behavior)")
                    content = reasoning_content
                else:
                    content = "{}"
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
                result = {"json_response": self._post_process_json_response(json_response, request.output_model_class)}
            else:
                # Structured output was requested but model failed to produce valid JSON.
                # This is a contract violation - raise instead of silently returning empty.
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
            # Standard text response - try to extract JSON if present
            # Issue #127: Check reasoning_content for models that use it
            content = message.content
            if not content:
                reasoning_content = getattr(message, 'reasoning_content', None)
                if reasoning_content:
                    logger.info("LMStudioAdapter: Found response in reasoning_content (model-specific behavior)")
                    content = reasoning_content
                else:
                    content = ""
            json_data = self._robustly_parse_json_from_text(content)
            if json_data:
                result = {"json_response": json_data, "text_response": content}
            else:
                result = {"text_response": content}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, result, latency_ms, self.model_name)
            return result

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """
        Invokes the model, dynamically using the 'response_format' parameter
        to enforce a JSON schema if a Pydantic model is provided in the request,
        as per LM Studio's documentation.
        """
        api_kwargs = self._build_request_kwargs(request)
        start_time = time.perf_counter()

        try:
            completion = self.client.chat.completions.create(**api_kwargs, timeout=self.timeout)
            return self._parse_completion(completion, request, api_kwargs, start_time)

        except OpenAIRateLimitError as e:
            error_message = f"LMStudio API rate limit exceeded: {e}"
            logger.error(error_message, exc_info=True)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, {"error": error_message}, latency_ms, self.model_name)
            raise RateLimitError(error_message) from e

        # Consolidated proxy/network error handling. These exceptions all indicate a failure
        # to communicate with the server, often due to a proxy block or network issue.
        except (APIConnectionError, PermissionDeniedError, httpx.ProxyError) as e:
            clean_message = ("A network error occurred, which is often due to a proxy blocking the request. "
                             "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted.")
            # Log the full error for debugging, but raise a clean message.
            logger.error(f"{clean_message} Original error: {e}", exc_info=True)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
            raise ProxyError(clean_message) from e

        except BadRequestError as e:
            if "context length" in str(e).lower():
                error_message = (f"LMStudio API context length error: {e}. This can happen if the configured "
                                 f"'context_window' in config.yaml is too large for the loaded model.")
                logger.error(error_message, exc_info=True)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": error_message}, latency_ms, self.model_name)
                raise LLMInvocationError(error_message) from e
            else:
                logger.error(f"LMStudio API BadRequestError: {e}", exc_info=True)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
                raise LLMInvocationError(f"LMStudio API BadRequestError: {e}") from e

        except Exception as e:
            logger.error(f"LMStudio API error during invoke: {e}", exc_info=True)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            capture_trace(request, {"error": str(e)}, latency_ms, self.model_name)
            raise LLMInvocationError(f"LMStudio API error: {e}") from e
