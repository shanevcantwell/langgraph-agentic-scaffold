# app/src/llm/llama_server_adapter.py
"""llama-server-specific adapter — thin subclass of LocalInferenceAdapter (#253).

Adds quirks that work around llama-server-specific behavior:
1. Schema enforcement skipped — llama-server's grammar converter can't handle
   oneOf schemas in response_format: json_schema. Falls back to prompt-based
   JSON + robust parser.
2. $ref inlining — same limitation as LM Studio; Pydantic-generated $defs/$ref
   must be flattened.
3. Thinking mode disabled — llama-server rejects assistant messages when
   Qwen3.5's thinking mode is enabled. Injects chat_template_kwargs to
   disable per-request.
"""
import logging
from typing import Dict, Any

from .local_inference_adapter import LocalInferenceAdapter
from .server_quirks import inline_schema_refs, _llama_server_extra_body

logger = logging.getLogger(__name__)


class LlamaServerAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter with llama-server-specific quirks.

    All core protocol logic (request building, response parsing, context pruning)
    lives in LocalInferenceAdapter. This subclass overrides hooks where
    llama-server deviates from the standard OpenAI chat completions protocol.
    """

    def __init__(self, *args, **kwargs):
        # Force skip_schema_enforcement — llama-server can't handle oneOf in json_schema
        if "model_config" in kwargs:
            kwargs["model_config"] = dict(kwargs["model_config"])
            kwargs["model_config"]["skip_schema_enforcement"] = True
        elif args:
            # model_config is the first positional arg
            args = list(args)
            args[0] = dict(args[0])
            args[0]["skip_schema_enforcement"] = True
            args = tuple(args)
        super().__init__(*args, **kwargs)

    # --- Hook overrides ---
    # Note: _resolve_schema_refs is NOT overridden here. LlamaServerAdapter forces
    # skip_schema_enforcement=True, so _build_tool_call_schema (the only caller of
    # _resolve_schema_refs) is never reached. The pooled path handles $ref inlining
    # via ServerQuirks in server_quirks.py.

    def _build_request_kwargs(self, request) -> Dict[str, Any]:
        """Build request kwargs with llama-server thinking mode disabled."""
        api_kwargs = super()._build_request_kwargs(request)

        # Merge thinking mode disablement into extra_body
        extra_injections = _llama_server_extra_body()
        if extra_injections:
            existing_extra = api_kwargs.get("extra_body", {})
            existing_extra.update(extra_injections)
            api_kwargs["extra_body"] = existing_extra

        return api_kwargs
