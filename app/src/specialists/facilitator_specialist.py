import logging
from typing import Dict, Any
from .base import BaseSpecialist
from ..interface.context_schema import ContextPlan, ContextActionType

logger = logging.getLogger(__name__)

class FacilitatorSpecialist(BaseSpecialist):
    """
    Orchestrates the execution of a ContextPlan by calling other specialists
    via MCP (Synchronous Service Invocation).
    """
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
                    # Call Researcher via MCP
                    results = self.mcp_client.call(
                        service_name="researcher_specialist",
                        function_name="search",
                        query=action.target
                    )
                    # Format results
                    formatted_results = "\n".join([f"- [{r.get('title')}]({r.get('url')}): {r.get('snippet')}" for r in results]) if isinstance(results, list) else str(results)
                    gathered_context.append(f"### Research: {action.target}\n{formatted_results}")
                    
                elif action.type == ContextActionType.READ_FILE:
                    # Call FileSpecialist via MCP
                    content = self.mcp_client.call(
                        service_name="file_specialist",
                        function_name="read_file",
                        path=action.target
                    )
                    gathered_context.append(f"### File: {action.target}\n```\n{content}\n```")
                    
                elif action.type == ContextActionType.SUMMARIZE:
                    # Call Summarizer via MCP
                    text_to_summarize = action.target
                    
                    # Heuristic: If target looks like a file path, try to read it first
                    if text_to_summarize.startswith("/") or text_to_summarize.startswith("./"):
                        try:
                             text_to_summarize = self.mcp_client.call(
                                service_name="file_specialist",
                                function_name="read_file",
                                path=text_to_summarize
                            )
                        except Exception:
                            # If read fails, assume it's raw text and proceed
                            pass
                    
                    summary = self.mcp_client.call(
                        service_name="summarizer_specialist",
                        function_name="summarize",
                        text=text_to_summarize
                    )
                    gathered_context.append(f"### Summary: {action.target}\n{summary}")
                    
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
