# app/src/llm/server_quirks.py
"""Per-server-type protocol quirks — extracted from LMStudioAdapter (#253).

Each inference server software (LM Studio, llama-server, vLLM, etc.) has
protocol-level differences from the OpenAI chat completions spec. This module
defines a ServerQuirks dataclass that captures those differences, and a registry
that maps server_type strings to their quirk implementations.

The PooledLocalInferenceAdapter looks up quirks by server_type after acquiring
a server slot, so the right quirks fire per-endpoint regardless of what software
runs there. Non-pooled adapters (LMStudioAdapter, LlamaServerAdapter) use
the same extracted functions directly.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared quirk functions — extracted from LMStudioAdapter
# ---------------------------------------------------------------------------

# #219: Harmony format control tokens (gpt-oss o200k_harmony encoding, IDs 200002-200012).
_HARMONY_TOKEN_RE = re.compile(r'<\|(?:start|end|channel|message|constrain|call|return)\|>')


def strip_harmony_tokens(content: str) -> str:
    """Strip Harmony special tokens from response text.

    gpt-oss models emit multi-channel responses like:
        <|channel|>final <|constrain|>SystemPlan<|message|>{...json...}
    This strips the control tokens so JSON extraction can find the payload.
    """
    if _HARMONY_TOKEN_RE.search(content):
        logger.info("Stripping Harmony tokens from response")
        return _HARMONY_TOKEN_RE.sub('', content)
    return content


def inline_schema_refs(node: Any, defs: Dict[str, Any]) -> Any:
    """Recursively resolve $ref pointers by inlining definitions from $defs.

    LM Studio and llama-server don't support JSON Schema $defs/$ref.
    Pydantic v2 generates $defs for nested model types (e.g., List[ParallelCall]).
    This walks a schema node and replaces every $ref with the actual definition,
    producing a flat schema the server can enforce.
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
            return inline_schema_refs(dict(resolved), defs)

        # Otherwise recurse into each value
        return {k: inline_schema_refs(v, defs) for k, v in node.items()}

    if isinstance(node, list):
        return [inline_schema_refs(item, defs) for item in node]

    return node


def force_empty_content_on_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure assistant messages with tool_calls have content="" (not null).

    LM Studio requires content to be a string, not null/None, when tool_calls
    are present. This is a no-op on servers that accept null content.
    """
    for msg in messages:
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            msg["content"] = ""
    return messages


def _noop_preprocess(content: str) -> str:
    return content


def _noop_format_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return messages


def _noop_resolve_refs(node: Any, defs: Dict[str, Any]) -> Any:
    return node


def _no_extra_body() -> Dict[str, Any]:
    return {}


def _llama_server_extra_body() -> Dict[str, Any]:
    """Inject chat_template_kwargs to disable thinking mode per-request.

    llama-server rejects assistant messages when Qwen3.5's thinking mode is
    enabled. Per-request control is documented as unreliable (llama.cpp #13160),
    so if this doesn't work, require --reasoning-format none as a launch flag.
    """
    return {"chat_template_kwargs": {"enable_thinking": False}}


# ---------------------------------------------------------------------------
# ServerQuirks dataclass
# ---------------------------------------------------------------------------

@dataclass
class ServerQuirks:
    """Protocol quirk set for a specific inference server type.

    Each field captures one dimension where server behavior diverges from the
    standard OpenAI chat completions protocol.
    """
    preprocess_response: Callable[[str], str]
    resolve_schema_refs: Callable[[Any, Dict[str, Any]], Any]
    format_messages_post: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]
    skip_schema_enforcement: bool
    extra_body_injections: Callable[[], Dict[str, Any]]


# ---------------------------------------------------------------------------
# Registry — maps server_type string to its quirk set
# ---------------------------------------------------------------------------

QUIRKS_REGISTRY: Dict[Optional[str], ServerQuirks] = {
    "lmstudio": ServerQuirks(
        preprocess_response=strip_harmony_tokens,
        resolve_schema_refs=inline_schema_refs,
        format_messages_post=force_empty_content_on_tool_calls,
        skip_schema_enforcement=False,
        extra_body_injections=_no_extra_body,
    ),
    "lmstudio_pool": ServerQuirks(
        preprocess_response=strip_harmony_tokens,
        resolve_schema_refs=inline_schema_refs,
        format_messages_post=force_empty_content_on_tool_calls,
        skip_schema_enforcement=False,
        extra_body_injections=_no_extra_body,
    ),
    "llama_server": ServerQuirks(
        preprocess_response=_noop_preprocess,
        resolve_schema_refs=inline_schema_refs,
        format_messages_post=_noop_format_messages,
        skip_schema_enforcement=True,
        extra_body_injections=_llama_server_extra_body,
    ),
    "llama_server_pool": ServerQuirks(
        preprocess_response=_noop_preprocess,
        resolve_schema_refs=inline_schema_refs,
        format_messages_post=_noop_format_messages,
        skip_schema_enforcement=True,
        extra_body_injections=_llama_server_extra_body,
    ),
    # Generic — all pass-through, no quirks
    None: ServerQuirks(
        preprocess_response=_noop_preprocess,
        resolve_schema_refs=_noop_resolve_refs,
        format_messages_post=_noop_format_messages,
        skip_schema_enforcement=False,
        extra_body_injections=_no_extra_body,
    ),
}


def get_quirks(server_type: Optional[str]) -> ServerQuirks:
    """Look up quirks for a server type, falling back to generic."""
    return QUIRKS_REGISTRY.get(server_type, QUIRKS_REGISTRY[None])
