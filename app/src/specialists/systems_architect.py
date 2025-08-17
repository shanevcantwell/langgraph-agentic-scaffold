import logging
import json
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt
from ..llm.clients import LLMInvocationError

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    def __init__(self, llm_provider: str):
        system_prompt = load_prompt("systems_architect")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        logger.info("---SYSTEMS ARCHITECT: Generating JSON Artifact---")
        try:
            initial_goal = state.get("messages", [])[-1].content
            if not initial_goal:
                return {"error": "SystemsArchitect Error: Initial goal not found in state."}

            messages = [
                SystemMessage(content=self.system_prompt_content),
                HumanMessage(content=initial_goal)
            ]
            
            parsed_json = self.llm_client.invoke(messages)
            
            logger.info("Successfully generated JSON artifact.")
            return {"json_artifact": json.dumps(parsed_json, indent=2), "error": None}

        except LLMInvocationError as e:
            error_message = f"Systems Architect failed due to LLM error: {e}"
            logger.error(error_message)
            return {"error": error_message}
        except Exception as e:
            error_message = f"An unexpected error occurred in SystemsArchitect: {e}"
            logger.error(error_message)
            return {"error": error_message}
