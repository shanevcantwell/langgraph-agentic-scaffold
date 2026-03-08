# app/src/llm/lmstudio_adapter.py
"""LM Studio-specific adapter — thin subclass of LocalInferenceAdapter.

Adds three quirks that work around LM Studio-specific behavior:
1. Harmony token stripping — gpt-oss models emit control tokens that must be
   stripped before JSON parsing.
2. $ref inlining — LM Studio's structured output engine doesn't support
   JSON Schema $defs/$ref, so Pydantic-generated schemas must be flattened.
3. content:"" — LM Studio requires assistant message content to be an empty
   string (not null) when tool_calls are present.
"""
import logging
import re
from typing import Dict, Any, List, Optional

from langchain_core.messages import BaseMessage

from .local_inference_adapter import LocalInferenceAdapter

logger = logging.getLogger(__name__)


class LMStudioAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter with LM Studio-specific quirks.

    All core protocol logic (request building, response parsing, context pruning)
    lives in LocalInferenceAdapter. This subclass only overrides the three hooks
    where LM Studio deviates from the standard OpenAI chat completions protocol.
    """

    # #219: Harmony format control tokens (gpt-oss o200k_harmony encoding, IDs 200002-200012).
    # These wrap the model's multi-channel output and must be stripped before JSON parsing.
    _HARMONY_TOKEN_RE = re.compile(r'<\|(?:start|end|channel|message|constrain|call|return)\|>')

    def _strip_harmony_tokens(self, text: str) -> str:
        """Strip Harmony special tokens from response text.

        gpt-oss models emit multi-channel responses like:
            <|channel|>final <|constrain|>SystemPlan<|message|>{...json...}
        This strips the control tokens so JSON extraction can find the payload.
        """
        return self._HARMONY_TOKEN_RE.sub('', text)

    # --- Hook overrides ---

    def _preprocess_response_content(self, content: str) -> str:
        """Strip Harmony control tokens before JSON parsing."""
        if self._HARMONY_TOKEN_RE.search(content):
            logger.info(f"{self.__class__.__name__}: Stripping Harmony tokens from response")
            return self._strip_harmony_tokens(content)
        return content

    def _resolve_schema_refs(self, node: Any, defs: Dict[str, Any]) -> Any:
        """Recursively resolve $ref pointers by inlining definitions from $defs.

        LM Studio's structured output engine doesn't support JSON Schema $defs/$ref.
        Pydantic v2 generates $defs for nested model types (e.g., List[ParallelCall]).
        This walks a schema node and replaces every $ref with the actual definition,
        producing a flat schema LM Studio can enforce.
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
                return self._resolve_schema_refs(dict(resolved), defs)

            # Otherwise recurse into each value
            return {k: self._resolve_schema_refs(v, defs) for k, v in node.items()}

        if isinstance(node, list):
            return [self._resolve_schema_refs(item, defs) for item in node]

        return node

    def _format_messages(
        self,
        messages: List[BaseMessage],
        use_json_tool_format: bool = False
    ) -> List[Dict[str, Any]]:
        """Format messages with LM Studio's content:"" quirk.

        LM Studio requires assistant message content to be an empty string
        (not null/None) when tool_calls are present. This override calls the
        base formatter then patches assistant messages accordingly.
        """
        api_messages = super()._format_messages(messages, use_json_tool_format)

        # LM Studio requires content to be string, not null, when tool_calls present
        for msg in api_messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                msg["content"] = ""

        return api_messages
