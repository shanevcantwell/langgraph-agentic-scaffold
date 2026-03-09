# app/src/llm/lmstudio_adapter.py
"""LM Studio-specific adapter — thin subclass of LocalInferenceAdapter.

Adds three quirks that work around LM Studio-specific behavior:
1. Harmony token stripping — gpt-oss models emit control tokens that must be
   stripped before JSON parsing.
2. $ref inlining — LM Studio's structured output engine doesn't support
   JSON Schema $defs/$ref, so Pydantic-generated schemas must be flattened.
3. content:"" — LM Studio requires assistant message content to be an empty
   string (not null) when tool_calls are present.

Quirk implementations are shared via server_quirks.py (#253) so the pooled
adapter can apply them per-endpoint based on server_type.
"""
import logging
from typing import Dict, Any, List

from langchain_core.messages import BaseMessage

from .local_inference_adapter import LocalInferenceAdapter
from .server_quirks import strip_harmony_tokens, inline_schema_refs, force_empty_content_on_tool_calls

logger = logging.getLogger(__name__)


class LMStudioAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter with LM Studio-specific quirks.

    All core protocol logic (request building, response parsing, context pruning)
    lives in LocalInferenceAdapter. This subclass only overrides the three hooks
    where LM Studio deviates from the standard OpenAI chat completions protocol.
    """

    # --- Hook overrides ---

    def _preprocess_response_content(self, content: str) -> str:
        """Strip Harmony control tokens before JSON parsing."""
        return strip_harmony_tokens(content)

    def _resolve_schema_refs(self, node: Any, defs: Dict[str, Any]) -> Any:
        """Inline $ref pointers — LM Studio doesn't support $defs/$ref."""
        return inline_schema_refs(node, defs)

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
        return force_empty_content_on_tool_calls(api_messages)
