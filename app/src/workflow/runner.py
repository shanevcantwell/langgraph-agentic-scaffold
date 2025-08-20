import logging
import os
from typing import Dict, Any
import json

from langchain_core.messages import HumanMessage

from ..graph.state import GraphState
# MODIFIED: Import is now from the local 'workflow' package
from .chief_of_staff import ChiefOfStaff

logger = logging.getLogger(__name__)

class WorkflowRunner:
    """
    A service class that encapsulates the logic for running the agentic workflow.
    This acts as a Facade, providing a simple interface to the complex internal system.
    """
    def __init__(self):
        """
        Initializes the WorkflowRunner by instantiating the ChiefOfStaff
        and compiling the LangGraph application.
        """
        chief_of_staff = ChiefOfStaff()
        
        self.app = chief_of_staff.get_graph()
        
        logger.info("WorkflowRunner initialized with compiled graph.")

    def run(self, goal: str) -> Dict[str, Any]:
        """
        Executes the workflow with a given goal.

        Args:
            goal: The high-level goal for the agentic system to accomplish.

        Returns:
            The final state of the graph after the workflow has completed.
        """
        logger.info(f"--- Starting workflow for goal: '{goal}' ---")
        
        # The initial state should conform to the GraphState TypedDict.
        # The router specialist is the entry point and will decide the first step based on the goal.
        initial_state: GraphState = {
            "messages": [HumanMessage(content=goal)],
            "next_specialist": None,
            "text_to_process": None,
            "extracted_data": None,
            "error": None,
            "json_artifact": None,
            "html_artifact": None,
        }

        try:
            final_state = self.app.invoke(initial_state)
            logger.info("--- Workflow completed successfully ---")
            return final_state
        except Exception as e:
            logger.error(f"--- Workflow failed with an unhandled exception: {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed catastrophically: {e}",
                "messages": [HumanMessage(content=goal)]
            }
