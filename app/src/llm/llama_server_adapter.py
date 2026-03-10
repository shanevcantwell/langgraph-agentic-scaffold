# app/src/llm/llama_server_adapter.py
"""llama-server-specific adapter — thin subclass of LocalInferenceAdapter (#253).

llama-server is the reference GBNF/PEG grammar implementation and handles JSON
schema enforcement natively. The only quirk needed is $ref inlining — llama-server
doesn't support JSON Schema $defs/$ref, so Pydantic-generated schemas must be
flattened before sending.

Thinking mode: grammar enforcement with thinking was broken until llama.cpp
commit 62b8143 ("Fix structured outputs #20223"). Builds after March 8 2026
handle this correctly. No per-request thinking suppression needed.

Note: $ref inlining is handled by server_quirks.py for the pooled path.
"""
import logging
from typing import Dict, Any, Optional

from .local_inference_adapter import LocalInferenceAdapter
from .server_quirks import inline_schema_refs

logger = logging.getLogger(__name__)


class LlamaServerAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter with llama-server-specific $ref inlining.

    All core protocol logic (request building, response parsing, context pruning)
    lives in LocalInferenceAdapter. This subclass exists as a named entry point
    for the adapter registry. Schema enforcement stays ON — llama-server handles
    it natively via GBNF grammar.

    Grammar works with thinking enabled on builds including 62b8143+.
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

    def _resolve_schema_refs(self, node: Any, defs: Dict[str, Any]) -> Any:
        """Inline $ref pointers — llama-server can't resolve nested refs (llama.cpp #8073)."""
        return inline_schema_refs(node, defs)
