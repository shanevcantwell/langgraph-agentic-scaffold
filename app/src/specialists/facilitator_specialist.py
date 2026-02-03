import logging
from typing import Dict, Any, Optional, List
from .base import BaseSpecialist
from .schemas import ReturnControlMode
from ..interface.context_schema import ContextPlan, ContextActionType
from ..mcp import sync_call_external_mcp, extract_text_from_mcp_result
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class FacilitatorSpecialist(BaseSpecialist):
    """
    Orchestrates the execution of a ContextPlan by calling other specialists
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

    def _assemble_resume_trace(self, artifacts: dict) -> Optional[List[dict]]:
        """
        Assemble trace for ReAct loop resumption (ADR-CORE-059: Memento fix).

        Instead of summarizing prior work in gathered_context (which creates conflicting
        sources of truth), we give the ReAct loop its actual prior trace. The model
        sees its own tool conversation and continues naturally.

        This replaces _summarize_prior_work() which used prompt engineering ("don't repeat
        these operations") instead of context engineering (give the model back its experience).

        Returns:
            List of trace entries (dicts) if traces exist, None otherwise.
            The specialist will deserialize these into ReActIteration objects.
        """
        all_traces: List[dict] = []

        # Collect all research_trace_N artifacts, sorted by index
        trace_keys = sorted(
            [k for k in artifacts.keys() if k.startswith("research_trace")],
            key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0
        )

        for trace_key in trace_keys:
            trace_data = artifacts.get(trace_key)
            if isinstance(trace_data, list):
                all_traces.extend(trace_data)

        if not all_traces:
            return None

        logger.info(f"Facilitator: Assembled {len(all_traces)} trace entries for resumption")
        return all_traces

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

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        
        # Determine Return Control Mode (Issue #96 / ADR-ROADMAP-001)
        exit_interview_result = artifacts.get("exit_interview_result")
        return_control = ReturnControlMode.ACCUMULATE # Default
        
        if exit_interview_result:
             mode_str = exit_interview_result.get("return_control", "accumulate")
             try:
                 return_control = ReturnControlMode(mode_str)
             except ValueError:
                 logger.warning(f"Facilitator: Unknown return_control '{mode_str}', defaulting to ACCUMULATE")

        logger.info(f"Facilitator: executing with mode {return_control.value}")

        # Handle Context Cleanup (RESET mode)
        existing_context = artifacts.get("gathered_context", "")
        if return_control == ReturnControlMode.RESET:
            logger.info("Facilitator: RESET mode - clearing gathered_context")
            existing_context = ""

        # DELTA mode not yet implemented (requires LLM capability) - fall back to ACCUMULATE
        if return_control == ReturnControlMode.DELTA:
            logger.warning("Facilitator: DELTA mode requested but not implemented, using ACCUMULATE")

        # Load original plan
        context_plan_data = artifacts.get("context_plan")
        if not context_plan_data:
            logger.warning("Facilitator: No 'context_plan' artifact found.")
            return {"error": "No context plan to execute."}
        try:
            context_plan = ContextPlan(**context_plan_data)
        except Exception as e:
            logger.error(f"Facilitator: Failed to parse ContextPlan: {e}")
            return {"error": f"Invalid context plan: {e}"}
            
        gathered_context = []
        logger.info(f"Facilitator: Executing plan with {len(context_plan.actions)} actions.")

        # Issue #100: Surface Exit Interview feedback for better routing decisions
        if exit_interview_result and not exit_interview_result.get("is_complete"):
            feedback = self._format_exit_interview_feedback(exit_interview_result)
            gathered_context.append(feedback)
            logger.info("Facilitator: Added Exit Interview feedback to gathered_context")

        if not self.mcp_client:
            logger.error("Facilitator: MCP Client not initialized.")
            return {"error": "MCP Client not initialized."}

        for action in context_plan.actions:
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
                    # Human-in-the-loop: pause graph execution for user clarification
                    from langgraph.types import interrupt

                    question_text = action.description or action.target or "Please clarify your request."

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

            except Exception as e:
                logger.error(f"Failed to execute action {action}: {e}")
                gathered_context.append(f"### Error: {action.target}\nFailed to execute: {e}")

        # ADR-CORE-059: Assemble resume trace for ReAct loop continuation (Memento fix)
        # However, we must generally AVOID this during Exit Interview retries (Issue #96/101),
        # because "resuming" a state where the agent thought it was done just makes it think it's done again.
        # Retry loops should be "fresh attempts with feedback", not "continuations of efficient failure".
        resume_trace = None
        
        # Only use resume_trace if we are NOT driven by an Exit Interview rejection,
        # OR if we are explicitly told to ACCUMULATE (and it wasn't a logic error).
        # But for now, safe default: if missing elements identified, start fresh.
        if not exit_interview_result:
            resume_trace = self._assemble_resume_trace(artifacts)
        elif return_control == ReturnControlMode.ACCUMULATE and artifacts.get("max_iterations_exceeded"):
            # Exception: If we stopped because we ran out of steps (not logic error), DO resume
            resume_trace = self._assemble_resume_trace(artifacts)
            logger.info("Facilitator: Resuming trace because failure was due to iteration limit")
        else:
            logger.info("Facilitator: Skipping resume_trace assembly to force fresh attempt (Exit Interview retry)")

        # Assemble final payload - Issue #96: ACCUMULATE existing + new context
        new_context = "\n\n".join(gathered_context)
        if existing_context:
            # Preserve previous context, append new with separator
            final_context = f"{existing_context}\n\n---\n\n{new_context}"
            logger.info(f"Facilitator: Accumulated context (existing: {len(existing_context)} chars + new: {len(new_context)} chars)")
        else:
            final_context = new_context

        result = {
            "artifacts": {
                "gathered_context": final_context
            },
            "scratchpad": {
                "facilitator_complete": True
            }
        }

        # Add resume_trace if we have prior work to continue from
        if resume_trace:
            result["artifacts"]["resume_trace"] = resume_trace
            logger.info(f"Facilitator: Added resume_trace with {len(resume_trace)} entries")

        return result
