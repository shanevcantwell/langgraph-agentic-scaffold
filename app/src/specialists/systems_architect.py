import logging
import json
from typing import Dict, Any

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    def __init__(self):
        super().__init__(specialist_name="systems_architect")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        logger.info("---SYSTEMS ARCHITECT: Generating JSON Artifact---")
        initial_goal = state.get("messages", [])[-1].content
        if not initial_goal:
            return {"error": "SystemsArchitect Error: Initial goal not found in state."}
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=initial_goal)],
            output_schema={
                "diagram_type": "sequence",
                "title": "User Login Flow",
                "participants": [
                    {
                        "id": "user",
                        "name": "User",
                        "type": "actor"
                    }
                ],
                "flow": [
                    {
                        "from": "user",
                        "to": "webapp",
                        "action": "Submit credentials",
                        "is_reply": False
                    }
                ]
            }
        )

        try:
            response_data = self.llm_adapter.invoke(request)
            logger.info("Successfully generated JSON artifact.")
            return {"json_artifact": json.dumps(response_data, indent=2), "error": None}
        except Exception as e:
            error_message = f"An unexpected error occurred in SystemsArchitect: {e}"
            logger.error(error_message)
            return {"error": error_message}