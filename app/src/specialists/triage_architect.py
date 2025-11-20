import logging
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..interface.context_schema import ContextPlan
from ..utils.prompt_loader import load_prompt
from ..llm.adapter import StandardizedLLMRequest
from ..utils.errors import SpecialistError

logger = logging.getLogger(__name__)

class TriageArchitect(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # LLM adapter is injected by GraphBuilder via _attach_llm_adapter

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise SpecialistError(f"LLM Adapter not attached to {self.specialist_name}")

        # 1. Get user input
        messages = state.get("messages", [])
        
        # Find the last HumanMessage to ensure we are processing the user's actual request,
        # not a routing instruction from the Router (which is an AIMessage).
        user_input = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_input = msg.content
                break
        
        if not user_input:
            # Fallback: If no HumanMessage is found (unlikely), use the last message content
            # but log a warning.
            if messages:
                logger.warning("TriageArchitect could not find a HumanMessage. Using last message content.")
                user_input = messages[-1].content
            else:
                logger.warning("TriageArchitect received no messages.")
                return {}
            
        # Check for uploaded image (Blind Triage Support)
        if state.get("artifacts", {}).get("uploaded_image.png"):
            user_input += "\n\n[SYSTEM NOTE: The user has uploaded an image. You cannot see it, but it is available in the artifacts. Do not ask for the image.]"

        # 2. Build Prompt
        prompt_file = self.specialist_config.get("prompt_file")
        if prompt_file:
            try:
                system_prompt = load_prompt(prompt_file)
            except Exception as e:
                logger.warning(f"Failed to load prompt file '{prompt_file}': {e}. Using fallback.")
                system_prompt = self._get_fallback_prompt()
        else:
            system_prompt = self._get_fallback_prompt()
        
        # 3. Create Request
        request = StandardizedLLMRequest(
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ],
            tools=[ContextPlan],
            force_tool_call=True
        )
        
        # 4. Invoke LLM
        try:
            response_data = self.llm_adapter.invoke(request)
            tool_calls = response_data.get("tool_calls", [])
            
            if not tool_calls:
                logger.warning("TriageArchitect LLM did not return a tool call.")
                return {"error": "Failed to generate context plan."}
                
            # Extract the first tool call (ContextPlan)
            plan_args = tool_calls[0]['args']
            
            # Validate against Pydantic model (optional but good practice)
            context_plan = ContextPlan(**plan_args)
            
            logger.info(f"TriageArchitect generated plan with {len(context_plan.actions)} actions.")
            
            # 5. Return Artifact
            return {
                "artifacts": {
                    "context_plan": context_plan.model_dump()
                },
                "scratchpad": {
                    "triage_reasoning": context_plan.reasoning
                }
            }
            
        except Exception as e:
            logger.error(f"Error in TriageArchitect: {e}", exc_info=True)
            return {"error": str(e)}

    def _get_fallback_prompt(self) -> str:
        return """You are the Triage Architect. Your goal is to create a structured plan to gather context for the user's request.
        
        Analyze the user's request and determine what information is needed to answer it fully.
        You have access to the following context gathering actions:
        
        1. RESEARCH: Search the web for real-time information.
           - Use this for current events, documentation, or facts not in your training data.
           - Target: The search query.
           
        2. READ_FILE: Read a specific file from the workspace.
           - Use this when the user refers to a file or you need to inspect code/docs.
           - Target: The absolute file path.
           
        3. SUMMARIZE: Summarize a large text or document.
           - Use this to condense information.
           - Target: The text or file path to summarize.
           
        Output a ContextPlan containing a list of these actions.
        If no context gathering is needed (e.g., a simple greeting), return an empty list of actions.
        """
