import logging
import json
from typing import Dict, Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..interface.project_context import ProjectContext, ProjectState
from ..utils.errors import SpecialistError
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class ProjectDirector(BaseSpecialist):
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        # 1. Get or Initialize ProjectContext
        artifacts = state.get("artifacts", {})
        project_context_data = artifacts.get("project_context")
        
        if not project_context_data:
            # Initialize from user request
            messages = state.get("messages", [])
            user_request = messages[-1].content if messages else "Unknown Goal"
            project_context = ProjectContext(project_goal=user_request)
            logger.info(f"Initialized new ProjectContext: {project_context.project_goal}")
        else:
            project_context = ProjectContext(**project_context_data)

        # 2. Get last result (from WebSpecialist)
        # WebSpecialist returns {"search_results": ...} or {"error": ...} which are merged into state
        last_result = state.get("search_results")
        if not last_result:
             last_result = state.get("error")
        
        # 3. Prepare Prompt
        context_str = f"""
        Current Project Context:
        Goal: {project_context.project_goal}
        Knowledge Base: {json.dumps(project_context.knowledge_base, indent=2)}
        Open Questions: {json.dumps(project_context.open_questions, indent=2)}
        Iteration: {project_context.iteration}
        
        Last Result:
        {last_result if last_result else "None (First Turn)"}
        """
        
        # Construct messages
        # We rely on the adapter's configured system prompt to set the persona.
        # We send the context as a user message.
        messages = [
            HumanMessage(content=context_str)
        ]
        
        # 4. Call LLM
        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)
        
        # 5. Parse Response
        content = response_data.get("content", "")
        try:
            # Extract JSON (simple heuristic)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            decision = json.loads(content)
        except Exception as e:
            logger.error(f"Failed to parse ProjectDirector response: {e}")
            raise SpecialistError(f"ProjectDirector failed to parse JSON: {e}")

        # 6. Update Context
        updates = decision.get("updates", {})
        for k in updates.get("add_knowledge", []):
            project_context.add_knowledge(k)
        for q in updates.get("remove_questions", []):
            project_context.remove_question(q)
        for q in updates.get("add_questions", []):
            project_context.add_question(q)
            
        project_context.iteration += 1
        
        # 7. Handle Next Step
        next_step = decision.get("next_step", {})
        action_type = next_step.get("type")
        payload = next_step.get("payload")
        
        new_scratchpad = {}
        
        if action_type == "SEARCH":
            new_scratchpad["web_task"] = {"capability": "search", "params": {"query": payload}}
            new_scratchpad["next_worker"] = "web_specialist"
        elif action_type == "BROWSE":
            new_scratchpad["web_task"] = {"capability": "browse", "params": {"url": payload}}
            new_scratchpad["next_worker"] = "web_specialist"
        elif action_type == "COMPLETE":
            project_context.update_state(ProjectState.COMPLETE)
            new_scratchpad["final_answer"] = payload
            new_scratchpad["next_worker"] = "router" # Return to router
            
        # Save updated context
        artifacts["project_context"] = project_context.dict()
        
        return {
            "artifacts": artifacts,
            "scratchpad": new_scratchpad
        }
