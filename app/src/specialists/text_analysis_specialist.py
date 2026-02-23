# app/src/specialists/text_analysis_specialist.py
"""
Text analysis specialist — absorbs data_extractor and data_processor roles.

Two execution modes:
- **Single-pass** (default): Text in, structured analysis out. No tools needed.
- **ReAct** (via prompt-prix MCP react_step): Iterative tool use for data
  operations (read files, format JSON, convert data, measure drift).
  Activated when external_mcp_client can reach prompt-prix service.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..mcp import sync_call_external_mcp, extract_text_from_mcp_result, make_terminal_trace_entry
from .schemas import TextAnalysis

logger = logging.getLogger(__name__)

# Tool parameter schemas for OpenAI tool format
_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
    "read_file": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "File path to read"}},
        "required": ["path"],
    },
    "list_directory": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Directory path to list"}},
        "required": ["path"],
    },
    "calculate_drift": {
        "type": "object",
        "properties": {
            "text_a": {"type": "string", "description": "First text"},
            "text_b": {"type": "string", "description": "Second text"},
        },
        "required": ["text_a", "text_b"],
    },
    "analyze_variants": {
        "type": "object",
        "properties": {
            "variants": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of prompt variant strings",
            }
        },
        "required": ["variants"],
    },
    "format_json": {
        "type": "object",
        "properties": {"json": {"type": "string", "description": "JSON string to format"}},
        "required": ["json"],
    },
    "convert_json_to_csv": {
        "type": "object",
        "properties": {"json": {"type": "string", "description": "JSON array string to convert"}},
        "required": ["json"],
    },
    "convert_json_to_yaml": {
        "type": "object",
        "properties": {"json": {"type": "string", "description": "JSON string to convert"}},
        "required": ["json"],
    },
}


class _ToolDef:
    """Lightweight tool definition mapping tool names to MCP services."""
    __slots__ = ("service", "function", "description")

    def __init__(self, service: str, function: str, description: str = ""):
        self.service = service
        self.function = function
        self.description = description


class TextAnalysisSpecialist(BaseSpecialist):
    """
    Analyzes, summarizes, extracts, or transforms text and structured data.

    Absorbs the former data_extractor_specialist (LLM + schema) and
    data_processor_specialist (procedural stamp). When prompt-prix MCP
    is reachable, can iteratively use filesystem, terminal, semantic-chunker,
    and it-tools MCP services for structured data operations via react_step().
    """

    DEFAULT_MAX_ITERATIONS = 10

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        artifacts = state.get("artifacts", {})
        text_to_process = artifacts.get("text_to_process")
        gathered_context = artifacts.get("gathered_context", "")

        # ReAct capability: can we reach prompt-prix MCP for react_step?
        has_react = self._has_react_capability()

        # If we have ReAct tools and gathered_context suggests iterative work,
        # use the ReAct path. Otherwise, fast-path single-pass analysis.
        if has_react and self._should_use_tools(state):
            return self._execute_react(state, messages, gathered_context)

        return self._execute_single_pass(state, messages, text_to_process)

    def _has_react_capability(self) -> bool:
        """Check if prompt-prix MCP is reachable for react_step calls."""
        return (
            hasattr(self, 'external_mcp_client')
            and self.external_mcp_client is not None
            and self.external_mcp_client.is_connected("prompt-prix")
        )

    def _should_use_tools(self, state: Dict[str, Any]) -> bool:
        """
        Heuristic: use tools when the task likely needs iterative operations.

        Tool use is warranted when:
        - There's gathered_context from Facilitator (suggests a complex task)
        - There's no text_to_process artifact (may need to read files first)
        - The user's request mentions file operations or data transformation
        """
        artifacts = state.get("artifacts", {})
        gathered_context = artifacts.get("gathered_context", "")
        text_to_process = artifacts.get("text_to_process")

        # If Facilitator provided gathered_context, this is a routed task — use tools
        if gathered_context and gathered_context.strip():
            return True

        # If no text artifact, we may need to read files to get input
        if not text_to_process or not text_to_process.strip():
            return True

        return False

    def _execute_single_pass(
        self, state: Dict[str, Any], messages: List[BaseMessage], text_to_process: str
    ) -> Dict[str, Any]:
        """Original single-pass analysis: text in, structured TextAnalysis out."""
        if not text_to_process or not text_to_process.strip():
            logger.warning("TextAnalysisSpecialist: no text_to_process artifact and no ReAct tools.")
            ai_message = create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content="I cannot run because there is no text to process and no tools to gather it."
            )
            return {"messages": [ai_message]}

        contextual_messages = messages + [
            HumanMessage(
                content=(
                    f"The following document has been provided as context:\n\n"
                    f"---\n{text_to_process}\n---\n\n"
                    f"Perform the analysis requested by the user above."
                )
            )
        ]

        request = StandardizedLLMRequest(
            messages=contextual_messages, output_model_class=TextAnalysis
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("TextAnalysisSpecialist failed to get a valid JSON response from the LLM.")

        report = f"I have analyzed the text as requested.\n\n**Summary:**\n{json_response.get('summary', 'N/A')}\n\n**Main Points:**\n"
        for point in json_response.get("main_points", []):
            report += f"- {point}\n"

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=report,
        )

        pass_num = len(state.get("artifacts", {}).get("text_analysis_results", []))
        summary_blurb = f"### Text Analysis (pass {pass_num})\n{report}"

        return {
            "messages": [ai_message],
            "artifacts": {
                "text_analysis_results": self._append_result(state, {
                    "status": "complete",
                    "summary": report,
                    "data": json_response,
                }),
                "gathered_context": self._append_to_gathered_context(state, summary_blurb),
            },
        }

    # ─── ReAct path via prompt-prix MCP react_step() ───────────────────

    def _execute_react(
        self, state: Dict[str, Any], messages: List[BaseMessage], gathered_context: str
    ) -> Dict[str, Any]:
        """ReAct path: iterative tool use via prompt-prix MCP react_step()."""
        tools = self._build_tools()
        task_prompt = self._build_task_prompt(state, gathered_context)
        tool_schemas = self._build_openai_tool_schemas(tools)
        model_id = getattr(self.llm_adapter, 'model_name', None) or "default"
        system_prompt = self.llm_adapter.system_prompt if hasattr(self.llm_adapter, 'system_prompt') else ""
        max_iterations = self._get_max_iterations()

        trace: List[Dict[str, Any]] = []
        call_counter = 0

        for iteration in range(max_iterations):
            try:
                raw_result = sync_call_external_mcp(
                    self.external_mcp_client,
                    "prompt-prix",
                    "react_step",
                    {
                        "model_id": model_id,
                        "system_prompt": system_prompt,
                        "initial_message": task_prompt,
                        "trace": trace,
                        "mock_tools": None,
                        "tools": tool_schemas,
                        "call_counter": call_counter,
                    },
                    timeout=600.0,
                )

                # Parse MCP CallToolResult → dict
                result = self._parse_react_step_result(raw_result)

                # Permission denied or parse error returns a string
                if isinstance(result, str):
                    logger.error(f"TextAnalysisSpecialist react_step returned error: {result}")
                    trace.append(make_terminal_trace_entry("ERROR", iteration, result, False))
                    return self._build_error_result(state, result, trace)

                call_counter = result.get("call_counter", call_counter)

                if result.get("completed"):
                    final_response = result.get("final_response", "Analysis complete.")
                    # #215: Record DONE in trace from prompt-prix done_trace_entry
                    done_entry = result.get("done_trace_entry")
                    if done_entry:
                        done_entry["iteration"] = iteration
                        done_entry["observation"] = final_response
                        done_entry["success"] = True
                        trace.append(done_entry)
                    else:
                        trace.append(make_terminal_trace_entry("DONE", iteration, final_response, True))
                    logger.info(
                        f"TextAnalysisSpecialist completed after {iteration + 1} iterations, "
                        f"{len(trace)} tool calls"
                    )
                    return self._build_success_result(state, final_response, trace)

                # Dispatch pending tool calls to real MCP services
                pending = result.get("pending_tool_calls", [])
                thought = result.get("thought")

                if not pending:
                    no_tools_msg = "react_step returned no tool calls and no completion"
                    logger.warning(no_tools_msg)
                    trace.append(make_terminal_trace_entry("NO_TOOLS", iteration, no_tools_msg, False))
                    return self._build_error_result(state, no_tools_msg, trace)

                for tc in pending:
                    observation = self._dispatch_tool_call(tc, tools)
                    trace.append({
                        "iteration": iteration,
                        "tool_call": {
                            "id": tc.get("id", f"call_{call_counter}"),
                            "name": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        },
                        "observation": observation,
                        "success": not observation.startswith("Error:"),
                        "thought": thought,
                    })

            except Exception as e:
                error_msg = f"react loop error at iteration {iteration}: {e}"
                logger.error(f"TextAnalysisSpecialist {error_msg}")
                trace.append(make_terminal_trace_entry("ERROR", iteration, str(e), False))
                return self._build_error_result(state, error_msg, trace)

        # Max iterations exceeded
        partial_msg = (
            f"Analysis reached iteration limit ({max_iterations}). "
            f"Partial progress:\n{self._summarize_trace_dicts(trace)}"
        )
        logger.warning(f"TextAnalysisSpecialist hit max iterations ({max_iterations})")
        trace.append(make_terminal_trace_entry(
            "MAX_ITERATIONS", max_iterations - 1,
            f"Reached {max_iterations} iterations without completion", False,
            {"max_iterations": max_iterations, "iterations_used": max_iterations},
        ))
        return self._build_partial_result(state, partial_msg, trace, max_iterations)

    def _parse_react_step_result(self, raw_result: Any) -> Any:
        """Parse MCP CallToolResult from react_step into a dict.

        sync_call_external_mcp returns either:
        - A string (permission denied from PermissionedMcpClient)
        - A dict (direct return in tests or future bridge changes)
        - A CallToolResult object (MCP SDK type with .content list)

        react_step returns JSON in the text content. We extract and parse it.
        """
        # Already a dict (direct return or test mock) → pass through
        if isinstance(raw_result, dict):
            return raw_result

        # Permission denied → already a string
        if isinstance(raw_result, str):
            return raw_result

        # Extract text from CallToolResult
        text = extract_text_from_mcp_result(raw_result)
        if not text:
            return "react_step returned empty response"

        # Parse JSON → dict
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return f"react_step returned non-dict JSON: {type(parsed).__name__}"
        except json.JSONDecodeError as e:
            # If it's not JSON, treat as plain text completion
            logger.warning(f"react_step returned non-JSON text: {e}")
            return {"completed": True, "final_response": text}

    def _dispatch_tool_call(
        self, pending: Dict[str, Any], tools: Dict[str, _ToolDef]
    ) -> str:
        """Dispatch a single pending tool call to the appropriate MCP service."""
        tool_name = pending.get("name", "")
        tool_args = pending.get("args", {})
        tool_def = tools.get(tool_name)

        if not tool_def:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            raw_result = sync_call_external_mcp(
                self.external_mcp_client,
                tool_def.service,
                tool_def.function,
                tool_args,
            )
            return extract_text_from_mcp_result(raw_result)
        except Exception as e:
            logger.error(f"Tool dispatch failed for {tool_name}: {e}")
            return f"Error: {tool_name} failed: {e}"

    # ─── Result builders ───────────────────────────────────────────────

    def _build_success_result(
        self, state: Dict[str, Any], final_response: str, trace: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        pass_num = len(state.get("artifacts", {}).get("text_analysis_results", []))
        summary_blurb = f"### Text Analysis (pass {pass_num})\n{final_response}"
        return {
            "messages": [AIMessage(content=final_response)],
            "artifacts": {
                "text_analysis_results": self._append_result(state, {
                    "status": "complete",
                    "summary": final_response,
                    "trace": trace,
                    "iterations": len(trace),
                }),
                "gathered_context": self._append_to_gathered_context(state, summary_blurb),
            },
            "scratchpad": {
                "react_trace": trace,
            },
        }

    def _build_error_result(
        self, state: Dict[str, Any], error_msg: str, trace: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        pass_num = len(state.get("artifacts", {}).get("text_analysis_results", []))
        summary_blurb = f"### Text Analysis (pass {pass_num}) — error\n{error_msg}"
        return {
            "messages": [AIMessage(content=error_msg)],
            "artifacts": {
                "text_analysis_results": self._append_result(state, {
                    "status": "error",
                    "summary": error_msg,
                    "trace": trace,
                    "iterations": len(trace),
                }),
                "gathered_context": self._append_to_gathered_context(state, summary_blurb),
            },
            "scratchpad": {
                "react_trace": trace,
            },
        }

    def _build_partial_result(
        self, state: Dict[str, Any], msg: str, trace: List[Dict[str, Any]], max_iter: int
    ) -> Dict[str, Any]:
        pass_num = len(state.get("artifacts", {}).get("text_analysis_results", []))
        summary_blurb = f"### Text Analysis (pass {pass_num}) — partial\n{msg}"
        return {
            "messages": [AIMessage(content=msg)],
            "artifacts": {
                "text_analysis_results": self._append_result(state, {
                    "status": "max_iterations",
                    "summary": msg,
                    "trace": trace,
                    "iterations": max_iter,
                }),
                "gathered_context": self._append_to_gathered_context(state, summary_blurb),
            },
            "scratchpad": {
                "react_trace": trace,
            },
        }

    # ─── Tool definitions ──────────────────────────────────────────────

    def _build_tools(self) -> Dict[str, _ToolDef]:
        """Define available tools mapping tool names to MCP service coordinates."""
        return {
            # Filesystem tools (external MCP)
            "read_file": _ToolDef(
                service="filesystem",
                function="read_file",
                description="Read the contents of a file. Args: path (str).",
            ),
            "list_directory": _ToolDef(
                service="filesystem",
                function="list_directory",
                description="List files and directories. Args: path (str).",
            ),
            # Semantic tools (external MCP)
            "calculate_drift": _ToolDef(
                service="semantic-chunker",
                function="calculate_drift",
                description="Cosine distance between two texts in embedding space (768-d embeddinggemma-300m). Args: text_a (str), text_b (str). Returns float 0.0-2.0.",
            ),
            "analyze_variants": _ToolDef(
                service="semantic-chunker",
                function="analyze_variants",
                description="Measure geometric distance between prompt phrasings. Args: variants (list[str]).",
            ),
            # IT tools (external MCP)
            "format_json": _ToolDef(
                service="it-tools",
                function="format_json",
                description="Pretty-print JSON. Args: json (str).",
            ),
            "convert_json_to_csv": _ToolDef(
                service="it-tools",
                function="convert_json_to_csv",
                description="Convert JSON array to CSV. Args: json (str).",
            ),
            "convert_json_to_yaml": _ToolDef(
                service="it-tools",
                function="convert_json_to_yaml",
                description="Convert JSON to YAML. Args: json (str).",
            ),
        }

    def _build_openai_tool_schemas(self, tools: Dict[str, _ToolDef]) -> List[Dict[str, Any]]:
        """Convert tool definitions to OpenAI function calling format for react_step."""
        schemas = []
        for name, tool_def in tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_def.description,
                    "parameters": _TOOL_PARAMS.get(name, {"type": "object", "properties": {}}),
                },
            })
        return schemas

    # ─── Prompt & config helpers ───────────────────────────────────────

    def _build_task_prompt(self, state: Dict[str, Any], gathered_context: str) -> str:
        """Build the task prompt from state and gathered context."""
        messages = state.get("messages", [])
        user_request = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_request = msg.content
                break

        parts = [f"## Task\n{user_request}"]
        if gathered_context:
            parts.append(f"\n## Context\n{gathered_context}")

        text_to_process = state.get("artifacts", {}).get("text_to_process")
        if text_to_process:
            parts.append(f"\n## Provided Text\n{text_to_process}")

        return "\n".join(parts)

    def _get_max_iterations(self) -> int:
        """Get max iterations from config, with fallback."""
        if hasattr(self, '_react_config') and self._react_config:
            return self._react_config.get('max_iterations', self.DEFAULT_MAX_ITERATIONS)
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _append_result(self, state: Dict[str, Any], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Append a result entry to the text_analysis_results list (read-append-write)."""
        existing = state.get("artifacts", {}).get("text_analysis_results", [])
        return existing + [entry]

    def _summarize_trace_dicts(self, trace: List[Dict[str, Any]]) -> str:
        """Summarize trace (list of dicts) for error messages."""
        if not trace:
            return "(no tool calls recorded)"
        lines = []
        for step in trace[-10:]:
            tc = step.get("tool_call", {})
            status = "ok" if step.get("success") else "FAIL"
            lines.append(f"  [{status}] {tc.get('name', '?')}({tc.get('args', {})})")
        return "\n".join(lines)
