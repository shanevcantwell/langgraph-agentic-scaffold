# app/src/specialists/text_analysis_specialist.py
"""
Text analysis specialist — absorbs data_extractor and data_processor roles.

Two execution modes:
- **Single-pass** (default): Text in, structured analysis out. No tools needed.
- **ReAct** (when tools available): Iterative tool use for data operations
  (read files, format JSON, convert data, measure drift). Activated by
  config.yaml `react: enabled: true` — the ReactEnabledSpecialist wrapper
  injects execute_with_tools() at load time (ADR-CORE-051).
"""
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from .mixins import ToolDef, MaxIterationsExceeded, StagnationDetected, ReActIteration
from ..llm.adapter import StandardizedLLMRequest
from .schemas import TextAnalysis

logger = logging.getLogger(__name__)


class TextAnalysisSpecialist(BaseSpecialist):
    """
    Analyzes, summarizes, extracts, or transforms text and structured data.

    Absorbs the former data_extractor_specialist (LLM + schema) and
    data_processor_specialist (procedural stamp). When ReAct is enabled
    via config, can iteratively use filesystem, terminal, semantic-chunker,
    and it-tools MCP services for structured data operations.
    """

    DEFAULT_MAX_ITERATIONS = 10

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        artifacts = state.get("artifacts", {})
        text_to_process = artifacts.get("text_to_process")
        gathered_context = artifacts.get("gathered_context", "")

        # Determine if we have ReAct capability (injected by ReactEnabledSpecialist wrapper)
        has_react = hasattr(self, 'execute_with_tools')

        # If we have ReAct tools and gathered_context suggests iterative work,
        # use the ReAct path. Otherwise, fast-path single-pass analysis.
        if has_react and self._should_use_tools(state):
            return self._execute_react(state, messages, gathered_context)

        return self._execute_single_pass(state, messages, text_to_process)

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

        return {
            "messages": [ai_message],
            "artifacts": {
                "text_analysis_report.md": report,
                "text_analysis": json_response,
            },
            "task_is_complete": True,
        }

    def _execute_react(
        self, state: Dict[str, Any], messages: List[BaseMessage], gathered_context: str
    ) -> Dict[str, Any]:
        """ReAct path: iterative tool use for complex data operations."""
        tools = self._build_tools()
        task_prompt = self._build_task_prompt(state, gathered_context)

        try:
            final_response, trace = self.execute_with_tools(
                task_prompt=task_prompt,
                tools=tools,
                max_iterations=self._get_max_iterations(),
                stop_on_error=False,
            )

            logger.info(f"TextAnalysisSpecialist completed after {len(trace)} tool calls")

            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=final_response)],
                "artifacts": {
                    trace_key: [self._serialize_react_iteration(step) for step in trace],
                    "iterations_used": len(trace),
                    "analysis_status": "complete",
                },
                "task_is_complete": True,
            }

        except StagnationDetected as e:
            logger.warning(
                f"TextAnalysisSpecialist stagnation: '{e.tool_name}' called "
                f"{e.repeat_count} times after {e.iterations} iterations"
            )
            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=f"Analysis stalled: repeatedly calling '{e.tool_name}'. Partial progress:\n{self._summarize_trace(e.history)}")],
                "artifacts": {
                    trace_key: [self._serialize_react_iteration(h) for h in e.history],
                    "iterations_used": e.iterations,
                    "analysis_status": "stagnated",
                },
            }

        except MaxIterationsExceeded as e:
            logger.warning(f"TextAnalysisSpecialist hit max iterations ({e.max_iterations})")
            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=f"Analysis reached iteration limit ({e.max_iterations}). Partial progress:\n{self._summarize_trace(e.history)}")],
                "artifacts": {
                    trace_key: [self._serialize_react_iteration(h) for h in e.history],
                    "iterations_used": e.max_iterations,
                    "analysis_status": "max_iterations",
                },
            }

    def _build_tools(self) -> Dict[str, ToolDef]:
        """Define available tools for ReAct loop."""
        return {
            # Filesystem tools (external MCP)
            "read_file": ToolDef(
                service="filesystem",
                function="read_file",
                description="Read the contents of a file. Args: path (str).",
            ),
            "list_directory": ToolDef(
                service="filesystem",
                function="list_directory",
                description="List files and directories. Args: path (str).",
            ),
            # Terminal tools (external MCP)
            "run_command": ToolDef(
                service="terminal",
                function="run_command",
                description="Execute a shell command. Args: command (str). Use for jq, yq, csvtool, sort, wc, grep.",
            ),
            # Semantic tools (external MCP)
            "calculate_drift": ToolDef(
                service="semantic-chunker",
                function="calculate_drift",
                description="Cosine distance between two texts in embedding space (768-d embeddinggemma-300m). Args: text_a (str), text_b (str). Returns float 0.0-2.0.",
            ),
            "analyze_variants": ToolDef(
                service="semantic-chunker",
                function="analyze_variants",
                description="Measure geometric distance between prompt phrasings. Args: variants (list[str]).",
            ),
            # IT tools (external MCP)
            "format_json": ToolDef(
                service="it-tools",
                function="format_json",
                description="Pretty-print JSON. Args: json (str).",
            ),
            "convert_json_to_csv": ToolDef(
                service="it-tools",
                function="convert_json_to_csv",
                description="Convert JSON array to CSV. Args: json (str).",
            ),
            "convert_json_to_yaml": ToolDef(
                service="it-tools",
                function="convert_json_to_yaml",
                description="Convert JSON to YAML. Args: json (str).",
            ),
        }

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

    def _get_trace_key(self, state: Dict[str, Any]) -> str:
        """Generate indexed trace key to preserve across invocations."""
        artifacts = state.get("artifacts", {})
        idx = 0
        while f"analysis_trace_{idx}" in artifacts:
            idx += 1
        return f"analysis_trace_{idx}"

    def _serialize_react_iteration(self, step: ReActIteration) -> Dict[str, Any]:
        """Serialize a ReActIteration for artifact storage."""
        return {
            "iteration": step.iteration,
            "tool": step.tool_call.name,
            "args": step.tool_call.args,
            "success": step.success,
            "thought": step.thought,
            "observation_preview": step.observation[:500] if step.observation else None,
        }

    def _summarize_trace(self, history) -> str:
        """Summarize tool call history for error messages."""
        if not history:
            return "(no tool calls recorded)"
        lines = []
        for step in history:
            status = "ok" if step.success else "FAIL"
            lines.append(f"  [{status}] {step.tool_call.name}({step.tool_call.args})")
        return "\n".join(lines[-10:])  # Last 10 calls
