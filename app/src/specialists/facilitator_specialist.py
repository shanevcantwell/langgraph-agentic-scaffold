import logging
from typing import Dict, Any, Optional
from .base import BaseSpecialist
from ..interface.context_schema import ContextPlan, ContextActionType
from ..mcp import sync_call_external_mcp, extract_text_from_mcp_result

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

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
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
                        formatted_items = "\n".join([f"- {item}" for item in items])
                        gathered_context.append(f"### Directory: {action.target}\n{formatted_items}")
                    else:
                        gathered_context.append(f"### Directory: {action.target}\n{str(items)}")

            except Exception as e:
                logger.error(f"Failed to execute action {action}: {e}")
                gathered_context.append(f"### Error: {action.target}\nFailed to execute: {e}")
                
        # Assemble final payload
        final_context = "\n\n".join(gathered_context)
        
        return {
            "artifacts": {
                "gathered_context": final_context
            },
            "scratchpad": {
                "facilitator_complete": True
            }
        }
