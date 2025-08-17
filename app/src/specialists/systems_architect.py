import logging
import json
import re
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    """
    A specialist that generates a system diagram as a JSON artifact from a high-level goal.
    It updates the GraphState directly with the result or an error.
    """
    def __init__(self, llm_provider: str):
        """
        Initializes the SystemsArchitect specialist.

        Args:
            llm_provider: The provider for the language model.
        """
        system_prompt = load_prompt("systems_architect")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Reads the initial goal from the state, invokes the LLM to generate a
        system diagram, and updates the state with either the JSON artifact or an error.

        Args:
            state: The current state of the graph.

        Returns:
            A dictionary to update the GraphState, containing either 'json_artifact'
            on success or 'error' on failure.
        """
        logger.info("---SYSTEMS ARCHITECT: Generating JSON Artifact---")
        
        try:
            initial_goal = state.get("messages", [])[-1].content
            if not initial_goal:
                error_message = "SystemsArchitect Error: Initial goal not found in state."
                logger.error(error_message)
                return {"error": error_message}

            messages = [
                SystemMessage(content=self.system_prompt_content),
                HumanMessage(content=initial_goal)
            ]
            
            # CORRECTED: Use the 'model' attribute, which is standard for LangChain clients.
            logger.info(f"Invoking LLM ({self.llm_client.model}) for JSON artifact generation.")
            llm_response = self.llm_client.invoke(messages)
            response_content = llm_response.content

            cleaned_content = re.sub(r"```(json)?\n(.*)\n```", r"\2", response_content, flags=re.DOTALL).strip()
            parsed_json = json.loads(cleaned_content)
            json_artifact_string = json.dumps(parsed_json, indent=2)

            logger.info("Successfully generated and validated JSON artifact.")
            return {"json_artifact": json_artifact_string, "error": None}

        except json.JSONDecodeError as e:
            error_message = f"SystemsArchitect Error: Failed to parse LLM response as JSON. Details: {e}"
            logger.error(error_message)
            logger.debug(f"Invalid content received: {response_content}")
            return {"error": error_message}
        
        except Exception as e:
            error_message = f"An unexpected error occurred in SystemsArchitect: {e}"
            logger.error(error_message)
            return {"error": error_message}

