# src/workflow/runner.py
import logging
import os
from ..utils.errors import ConfigError
from typing import Dict, Any
import json

from langchain_core.messages import HumanMessage

from ..graph.state import GraphState
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
        self.config = chief_of_staff.config
        self._perform_pre_flight_checks()
        self.recursion_limit = self.config.get("workflow", {}).get("recursion_limit", 25)
        self.app = chief_of_staff.get_graph()
        logger.info("WorkflowRunner initialized with compiled graph.")

    def _perform_pre_flight_checks(self):
        """
        Performs critical environment checks before the application is fully wired.
        This ensures the system fails fast if essential configurations are missing.
        """
        logger.info("Performing pre-flight environment checks...")
        llm_providers = self.config.get("llm_providers", {})
        
        # Determine which providers are actually in use by enabled specialists
        used_provider_bindings = set()
        for spec_config in self.config.get("specialists", {}).values():
            if binding := spec_config.get("llm_config"):
                used_provider_bindings.add(binding)

        for binding_key, provider_config in llm_providers.items():
            # Only check providers that are actually being used
            if binding_key not in used_provider_bindings:
                continue

            provider_type = provider_config.get("type")
            if provider_type == "gemini" and not provider_config.get("api_key"):
                raise ConfigError(
                    f"Pre-flight check failed: Provider '{binding_key}' is type 'gemini' but "
                    "the GOOGLE_API_KEY environment variable is not set."
                )
            elif provider_type == "lmstudio" and not provider_config.get("base_url"):
                raise ConfigError(
                    f"Pre-flight check failed: Provider '{binding_key}' is type 'lmstudio' but "
                    "the LMSTUDIO_BASE_URL environment variable is not set."
                )
        logger.info("Pre-flight environment checks passed successfully.")

    def run(self, goal: str) -> Dict[str, Any]:
        """
        Executes the workflow with a given goal.

        Args:
            goal: The high-level goal for the agentic system to accomplish.

        Returns:
            The final state of the graph after the workflow has completed.
        """
        logger.info(f"--- Starting workflow for goal: '{goal}' ---")
        
        initial_state: GraphState = {
            "messages": [HumanMessage(content=goal, name="user")],
            "next_specialist": None,
            "recommended_specialists": None,
            "text_to_process": None,
            "extracted_data": None,
            "error": None,
            "json_artifact": None,
            "html_artifact": None,
            "system_plan": None,
            "turn_count": 0,
            "routing_history": [],
            "archive_report": None,
            "web_builder_iteration": None,
            # Add the new field for preserving triage recommendations.
            "triage_recommendations": None,
            # Initialize the completion flag. This is critical for the router's
            # programmatic completion check to function correctly.
            "task_is_complete": False,
        }

        try:
            final_state = self.app.invoke(initial_state, config={"recursion_limit": self.recursion_limit})
            logger.info("--- Workflow completed successfully ---")
            return final_state
        except Exception as e:
            logger.error(f"--- Workflow failed with an unhandled exception: {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed catastrophically: {e}",
                "messages": [HumanMessage(content=goal)],
                "turn_count": 0, # Ensure a consistent return shape on catastrophic failure
            }
