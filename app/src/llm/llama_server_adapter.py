# app/src/llm/llama_server_adapter.py
"""llama-server-specific adapter — thin subclass of LocalInferenceAdapter (#253).

llama-server is the reference GBNF/PEG grammar implementation and handles JSON
schema enforcement natively. The only quirk needed is $ref inlining — llama-server
doesn't support JSON Schema $defs/$ref, so Pydantic-generated schemas must be
flattened before sending.

Thinking mode: if using a model with thinking (e.g. Qwen3.5), launch llama-server
with `--reasoning-format none` to disable thinking at the server level. Per-request
`chat_template_kwargs` control is unreliable (llama.cpp #13160) and conflicts with
assistant message prefill.

Note: $ref inlining is handled by server_quirks.py for the pooled path.
"""
import logging
from typing import Dict, Any, Optional

from .local_inference_adapter import LocalInferenceAdapter

logger = logging.getLogger(__name__)


class LlamaServerAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter with llama-server-specific $ref inlining.

    All core protocol logic (request building, response parsing, context pruning)
    lives in LocalInferenceAdapter. This subclass exists as a named entry point
    for the adapter registry. Schema enforcement stays ON — llama-server handles
    it natively via GBNF grammar.

    For thinking-capable models, require `--reasoning-format none` as a launch flag.
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        base_url: str,
        system_prompt: str,
        api_key: Optional[str] = None,
    ):
        super().__init__(model_config=model_config, base_url=base_url,
                         system_prompt=system_prompt, api_key=api_key)
