import logging
from typing import Dict, Any, Optional, List
from langgraph.errors import GraphInterrupt
from .base import BaseSpecialist
from ..interface.context_schema import ContextAction, ContextActionType
from ..mcp import sync_call_external_mcp, extract_text_from_mcp_result
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class FacilitatorSpecialist(BaseSpecialist):
    """
    Orchestrates triage actions by calling other specialists via MCP
    via MCP (Synchronous Service Invocation).

    Uses:
    - Internal MCP for web_specialist, summarizer_specialist
    - External MCP (filesystem container) for file operations (ADR-CORE-035)

    Note: external_mcp_client is injected by GraphBuilder after specialist loading.
    """

    def _is_filesystem_available(self) -> bool:
        """Check if external filesystem MCP is connected."""
        if not hasattr(self, 'external_mcp_client') or self.external_mcp_client is None:
            return False
        return self.external_mcp_client.is_connected("filesystem")

    def _read_file_via_filesystem_mcp(self, path: str) -> Optional[str]:
        """Read file content via external filesystem MCP."""
        if not self._is_filesystem_available():
            logger.warning("Facilitator: Filesystem MCP not available for file read")
            return None

        try:
            result = sync_call_external_mcp(
                self.external_mcp_client,
                "filesystem",
                "read_file",
                {"path": path}
            )
            return extract_text_from_mcp_result(result)
        except Exception as e:
            logger.error(f"Facilitator: Filesystem MCP read_file failed: {e}")
            raise

    def _list_directory_via_filesystem_mcp(self, path: str) -> Optional[list]:
        """List directory contents via external filesystem MCP."""
        if not self._is_filesystem_available():
            logger.warning("Facilitator: Filesystem MCP not available for directory list")
            return None

        try:
            result = sync_call_external_mcp(
                self.external_mcp_client,
                "filesystem",
                "list_directory",
                {"path": path}
            )
            # Parse the result - filesystem MCP returns structured directory listing
            text = extract_text_from_mcp_result(result)
            # The result may be JSON or newline-separated entries
            if text.startswith('['):
                import json
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
            # Fall back to line-by-line parsing
            return [line.strip() for line in text.split('\n') if line.strip()]
        except Exception as e:
            logger.error(f"Facilitator: Filesystem MCP list_directory failed: {e}")
            raise

    def _format_exit_interview_feedback(self, result: dict) -> str:
        """
        Format Exit Interview feedback using prompt template (#100).

        When Exit Interview marks a task INCOMPLETE, this surfaces what's left to do
        so Router and the destination specialist understand the continuation context.
        """
        template = load_prompt("exit_interview_feedback.md")
        return template.format(
            reasoning=result.get("reasoning", "Task needs additional work"),
            missing_elements=result.get("missing_elements", "Remaining work not specified"),
            recommended_specialists=", ".join(result.get("recommended_specialists", ["project_director"]))
        )

    def _summarize_work_in_progress(self, artifacts: dict, routing_history: list) -> Optional[str]:
        """
        Summarize work-in-progress for BENIGN interrupts (Issue #108).

        When max_iterations_exceeded is set (BENIGN interrupt), the specialist was
        mid-work. This surfaces what was happening so Router can make an informed
        decision about continuation.

        Without this context, Router sees "0 searches, 0 pages" (web-research framing)
        and picks the wrong specialist. With this context, Router sees the actual
        operations and continues with the correct specialist.

        Returns:
            Formatted work-in-progress summary, or None if not a BENIGN interrupt.
        """
        # Only for BENIGN interrupts (max_iterations without exit_interview_result)
        if not artifacts.get("max_iterations_exceeded"):
            return None

        # Find last non-planning specialist from routing_history
        planning_tags = {"planning", "context_engineering"}
        last_working_specialist = None

        # We need specialist configs to check tags, but we may not have them.
        # Fall back to known planning specialists by name.
        planning_specialists = {
            "triage_architect", "facilitator_specialist", "router_specialist"
        }

        for spec in reversed(routing_history):
            if spec not in planning_specialists:
                last_working_specialist = spec
                break

        if not last_working_specialist:
            return None

        # Collect all research_trace_N artifacts
        trace_keys = sorted(
            [k for k in artifacts.keys() if k.startswith("research_trace")],
            key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0
        )

        if not trace_keys:
            return None

        # Count operations by tool name across all traces
        tool_counts: Dict[str, int] = {}
        last_action = None
        total_ops = 0

        for trace_key in trace_keys:
            trace_data = artifacts.get(trace_key, [])
            if not isinstance(trace_data, list):
                continue

            for entry in trace_data:
                if not isinstance(entry, dict):
                    continue

                tool_name = entry.get("tool", "unknown")
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                total_ops += 1

                # Track last action for context
                if entry.get("success", True):
                    args = entry.get("args", {})
                    # Format last action based on tool type
                    if tool_name in ("move_file", "copy_file"):
                        source = args.get("source", "?")
                        dest = args.get("destination", "?")
                        last_action = f"{tool_name}({source} → {dest})"
                    elif tool_name in ("read_file", "list_directory", "create_directory"):
                        path = args.get("path", "?")
                        last_action = f"{tool_name}({path})"
                    else:
                        last_action = f"{tool_name}(...)"

        if total_ops == 0:
            return None

        # Format operations summary
        ops_summary = ", ".join(f"{tool}: {count}" for tool, count in sorted(tool_counts.items()))

        summary = f"""## Work In Progress

**Specialist:** {last_working_specialist}
**Operations completed:** {total_ops} ({ops_summary})
**Last action:** {last_action or "unknown"}
**Status:** Task interrupted mid-execution (max_iterations reached)

**Recommendation:** Continue with `{last_working_specialist}` to complete the work.
"""
        logger.info(f"Facilitator: Generated work-in-progress summary for {last_working_specialist} ({total_ops} ops)")
        return summary

    def _accumulate_prior_work(self, artifacts: dict, scratchpad: dict) -> list:
        """
        Accumulate specialist_activity across passes.

        Each PD pass writes a fresh specialist_activity to scratchpad (overwriting
        the previous via ior merge). Without accumulation, retry PD only sees the
        LATEST pass's operations — all prior work knowledge is lost.

        Facilitator curates the accumulation in an artifact so PD on pass N sees
        the work from passes 1 through N-1.
        """
        existing = artifacts.get("accumulated_work", [])
        new_activity = scratchpad.get("specialist_activity", [])
        if new_activity:
            combined = existing + new_activity
            logger.info(
                f"Facilitator: Accumulated work: {len(existing)} existing + "
                f"{len(new_activity)} new = {len(combined)} total entries"
            )
            return combined
        return existing

    def _build_task_context(self, artifacts: dict) -> list:
        """
        Build the task strategy section with full plan context.

        Includes plan_summary, execution_steps, and acceptance_criteria so that
        retry specialists have the complete plan — not just a one-line summary.
        """
        task_plan = artifacts.get("task_plan", {})
        parts = []

        summary = task_plan.get("plan_summary", "")
        if summary:
            section = f"### Task Strategy\n{summary}"

            steps = task_plan.get("execution_steps", [])
            if steps:
                section += "\n\n**Execution steps:**\n" + "\n".join(f"- {s}" for s in steps)

            criteria = task_plan.get("acceptance_criteria", "")
            if criteria:
                section += f"\n\n**Acceptance criteria:** {criteria}"

            parts.append(section)

        return parts

    def _build_prior_work_section(self, accumulated_work: list, exit_interview_result: dict = None) -> str:
        """
        Build the Prior Work section with accumulated operations and EI guidance.

        Includes EI's recommended next steps so the retry specialist knows
        both what was done AND what EI says should happen next.
        """
        lines = []

        if accumulated_work:
            lines.append("### Prior Work Completed")
            lines.extend(f"- {entry}" for entry in accumulated_work)

        # Append EI's recommended next steps so PD has actionable guidance
        if exit_interview_result and not exit_interview_result.get("is_complete", True):
            missing = exit_interview_result.get("missing_elements", "")
            if missing:
                lines.append("")
                lines.append("**EI recommended next steps:** " + missing)

        return "\n".join(lines) if lines else ""

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        exit_interview_result = artifacts.get("exit_interview_result")

        # ADR-077: Signal processor already classified this as BENIGN continuation.
        # routing_context persists because EI uses after_exit_interview edge (not signal_processor
        # path), so signals aren't overwritten between signal_processor and Facilitator.
        routing_context = state.get("signals", {}).get("routing_context")
        is_benign_continuation = routing_context == "benign_continuation"

        if is_benign_continuation:
            # BENIGN continuation: PD hit max_iterations but was making progress.
            # Surface prior work so Router has context for correct routing
            # and PD knows what it already did (without this, Router routes
            # to wrong specialist because gathered_context has no PD info).
            logger.info("Facilitator: BENIGN continuation (routing_context=benign_continuation)")

            scratchpad = state.get("scratchpad", {})
            context_parts = self._build_task_context(artifacts)

            if exit_interview_result and not exit_interview_result.get("is_complete", True):
                missing = exit_interview_result.get("missing_elements", "")
                if missing:
                    feedback = self._format_exit_interview_feedback(exit_interview_result)
                    context_parts.append(feedback)

            accumulated_work = self._accumulate_prior_work(artifacts, scratchpad)
            prior_work_section = self._build_prior_work_section(accumulated_work, exit_interview_result)
            if prior_work_section:
                context_parts.append(prior_work_section)

            result = {
                "artifacts": {
                    "accumulated_work": accumulated_work,
                },
            }

            if context_parts:
                result["artifacts"]["gathered_context"] = "\n\n".join(context_parts)
                logger.info("Facilitator: Added continuation context to BENIGN return")

            return result

        # Load triage actions from scratchpad (may be empty — Triage is a classifier,
        # not a context planner. Empty actions = PASS, which is the common case.)
        scratchpad = state.get("scratchpad", {})
        triage_actions_data = scratchpad.get("triage_actions", [])

        triage_actions = []
        for action_data in triage_actions_data:
            try:
                triage_actions.append(ContextAction(**action_data))
            except Exception as e:
                logger.warning(f"Facilitator: Skipping malformed action {action_data}: {e}")

        gathered_context = self._build_task_context(artifacts)
        logger.info(f"Facilitator: Assembling context ({len(triage_actions)} triage actions).")

        # Read routing_history early - needed for WIP summary
        routing_history = state.get("routing_history", [])

        # Issue #167 (revises #121): Curated EI feedback for retry guidance.
        # Only missing_elements + reasoning — no raw dumps, no routing data.
        if exit_interview_result and not exit_interview_result.get("is_complete", True):
            missing = exit_interview_result.get("missing_elements", "")
            if missing:
                feedback = self._format_exit_interview_feedback(exit_interview_result)
                gathered_context.append(feedback)
                logger.info("Facilitator: Added curated EI retry context")

        # Accumulate prior work across passes.
        # PD writes specialist_activity per pass; Facilitator accumulates in artifact
        # so retry PD sees work from ALL passes, not just the latest.
        accumulated_work = self._accumulate_prior_work(artifacts, scratchpad)
        if exit_interview_result and not exit_interview_result.get("is_complete", True):
            prior_work_section = self._build_prior_work_section(accumulated_work, exit_interview_result)
            if prior_work_section:
                gathered_context.append(prior_work_section)
                logger.info("Facilitator: Added accumulated prior work from scratchpad")

        # Issue #108: Surface work-in-progress for BENIGN interrupts
        # When max_iterations_exceeded WITHOUT exit_interview_result, this is a BENIGN
        # interrupt (not an Exit Interview retry). Router needs to know what specialist
        # was mid-work so it can continue correctly.
        if not exit_interview_result:
            wip_summary = self._summarize_work_in_progress(artifacts, routing_history)
            if wip_summary:
                gathered_context.append(wip_summary)
                logger.info("Facilitator: Added work-in-progress summary to gathered_context")

        # Execute triage actions via MCP (only if Triage produced any)
        if triage_actions and not self.mcp_client:
            logger.error("Facilitator: MCP Client not initialized.")
            return {"error": "MCP Client not initialized."}

        for action in triage_actions:
            try:
                logger.info(f"Facilitator: Executing action {action.type} -> {action.target}")
                
                if action.type == ContextActionType.RESEARCH:
                    # Call WebSpecialist via MCP
                    results = self.mcp_client.call(
                        service_name="web_specialist",
                        function_name="search",
                        query=action.target
                    )
                    # Format results
                    formatted_results = "\n".join([f"- [{r.get('title')}]({r.get('url')}): {r.get('snippet')}" for r in results]) if isinstance(results, list) else str(results)
                    gathered_context.append(f"### Research: {action.target}\n{formatted_results}")
                    
                elif action.type == ContextActionType.READ_FILE:
                    # Special handling: Check if target refers to an artifact already in state
                    # (e.g., uploaded images stored as base64, not filesystem files)
                    target_path = action.target

                    # Extract artifact key from paths like "/artifacts/image.png" or "uploaded_image.png"
                    if target_path.startswith("/artifacts/"):
                        artifact_key = target_path.replace("/artifacts/", "")
                    elif target_path.startswith("artifacts/"):
                        artifact_key = target_path.replace("artifacts/", "")
                    else:
                        artifact_key = target_path

                    # Check if this artifact exists in state (in-memory data)
                    if artifact_key in artifacts:
                        content = artifacts[artifact_key]
                        logger.info(f"Facilitator: Found '{artifact_key}' in artifacts (in-memory), skipping file read")

                        # Special formatting for base64 image data
                        if isinstance(content, str) and content.startswith("data:image/"):
                            gathered_context.append(f"### Image: {artifact_key}\n[Image data available in artifacts - {len(content)} chars]")
                        else:
                            # Regular text content
                            gathered_context.append(f"### Artifact: {artifact_key}\n```\n{content}\n```")
                    else:
                        # Not in artifacts, treat as filesystem path - call filesystem MCP
                        content = self._read_file_via_filesystem_mcp(target_path)
                        if content is None:
                            gathered_context.append(f"### File: {target_path}\n[Filesystem service unavailable]")
                        else:
                            gathered_context.append(f"### File: {target_path}\n```\n{content}\n```")
                    
                elif action.type == ContextActionType.SUMMARIZE:
                    # Call Summarizer via MCP
                    text_to_summarize = action.target

                    # Heuristic: If target looks like a file path, try to read it first
                    if text_to_summarize.startswith("/") or text_to_summarize.startswith("./"):
                        try:
                            file_content = self._read_file_via_filesystem_mcp(text_to_summarize)
                            if file_content:
                                text_to_summarize = file_content
                        except Exception:
                            # If read fails, assume it's raw text and proceed
                            pass

                    summary = self.mcp_client.call(
                        service_name="summarizer_specialist",
                        function_name="summarize",
                        text=text_to_summarize
                    )
                    gathered_context.append(f"### Summary: {action.target}\n{summary}")

                elif action.type == ContextActionType.LIST_DIRECTORY:
                    # Call filesystem MCP to list directory contents
                    items = self._list_directory_via_filesystem_mcp(action.target)
                    if items is None:
                        gathered_context.append(f"### Directory: {action.target}\n[Filesystem service unavailable]")
                    elif isinstance(items, list):
                        # Include full path for each item so downstream specialists have unambiguous paths
                        # Handle both string items and dict items (directory_tree returns dicts)
                        formatted_lines = []
                        for item in items:
                            if isinstance(item, dict):
                                # directory_tree format: {"name": "...", "type": "file/directory"}
                                name = item.get("name", str(item))
                                is_dir = item.get("type") == "directory"
                                prefix = "[DIR] " if is_dir else ""
                                formatted_lines.append(f"- {prefix}{action.target}/{name}")
                            elif isinstance(item, str):
                                if item.startswith('[DIR]'):
                                    formatted_lines.append(f"- [DIR] {action.target}/{item.replace('[DIR] ', '')}")
                                elif item.startswith('[FILE]'):
                                    formatted_lines.append(f"- [FILE] {action.target}/{item.replace('[FILE] ', '')}")
                                else:
                                    formatted_lines.append(f"- {action.target}/{item}")
                            else:
                                formatted_lines.append(f"- {action.target}/{str(item)}")
                        formatted_items = "\n".join(formatted_lines)
                        gathered_context.append(f"### Directory: {action.target}\n{formatted_items}")
                    else:
                        gathered_context.append(f"### Directory: {action.target}\n{str(items)}")

                elif action.type == ContextActionType.ASK_USER:
                    # On retry (EI result present), skip — stale trigger guard.
                    # ASK_USER is on hold pending ADR-032 (capability-based routing).
                    # See #179 for the architectural direction: clarification becomes
                    # reject-with-cause via final_user_response, not in-graph interrupt.
                    if exit_interview_result:
                        logger.info("Facilitator: Skipping ask_user on retry (user already clarified)")
                        continue

                    # Human-in-the-loop: pause graph execution for user clarification
                    from langgraph.types import interrupt

                    # For ASK_USER: target = the question to show the user,
                    # description = why this clarification is needed (meta)
                    question_text = action.target or action.description or "Please clarify your request."

                    interrupt_payload = {
                        "question": question_text,
                        "reason": action.description,
                        "action_type": "ask_user"
                    }

                    logger.info(f"Facilitator: Requesting user clarification: {question_text}")
                    user_answer = interrupt(interrupt_payload)

                    # Add clarification to gathered context (same pattern as other action types)
                    gathered_context.append(f"### User Clarification\n{user_answer}")
                    logger.info(f"Facilitator: Received clarification, added to gathered_context")

            except GraphInterrupt:
                # ASK_USER interrupt MUST propagate to LangGraph runner.
                # Unlike MCP errors (recoverable), GraphInterrupt is flow control.
                logger.info(f"Facilitator: GraphInterrupt raised for {action.type}, propagating")
                raise
            except Exception as e:
                logger.error(f"Failed to execute action {action}: {e}")
                gathered_context.append(f"### Error: {action.target}\nFailed to execute: {e}")

        final_context = "\n\n".join(gathered_context)

        return {
            "artifacts": {
                "gathered_context": final_context,
                "accumulated_work": accumulated_work,
            },
        }
