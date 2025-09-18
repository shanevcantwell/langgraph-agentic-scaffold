# src/workflow/runner.py
import logging
import os
from ..utils.errors import ConfigError
from typing import Dict, Any
from typing import AsyncGenerator

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
        self.chief_of_staff = chief_of_staff
        self.config = self.chief_of_staff.config
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

        # --- ADR-010: Fail-Fast Startup Validation ---
        workflow_config = self.config.get("workflow", {})
        critical_specialists = workflow_config.get("critical_specialists", [])
        if critical_specialists:
            loaded_specialist_names = self.chief_of_staff.specialists.keys()
            missing_critical = [name for name in critical_specialists if name not in loaded_specialist_names]
            if missing_critical:
                raise ConfigError(
                    f"Pre-flight check failed: The following critical specialists failed to load: {missing_critical}. "
                    "The application cannot start in this state. Please check the logs for errors related to these specialists."
                )
            logger.info(f"Successfully validated that all critical specialists are loaded: {critical_specialists}")

        logger.info("All pre-flight checks passed successfully.")

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

            final_artifacts = final_state.get("artifacts", {})
            final_response = final_artifacts.get("final_user_response.md", "Workflow completed, but no final user response was generated.")
            
            return {
                "final_user_response": final_response
            }

        except Exception as e:
            logger.error(f"--- Workflow failed with an unhandled exception: {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed catastrophically: {e}",
                "messages": [HumanMessage(content=goal)],
                "turn_count": 0, # Ensure a consistent return shape on catastrophic failure
            }

    async def run_streaming(self, goal: str) -> AsyncGenerator[str, None]:
        """
        Executes the workflow with a given goal and streams back real-time updates.

        Args:
            goal: The high-level goal for the agentic system to accomplish.

        Yields:
            A stream of strings, representing log messages or the final state.
        """
        logger.info(f"--- Starting streaming workflow for goal: '{goal}' ---")
        
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
            "triage_recommendations": None,
            "task_is_complete": False,
        }
        final_state = None
        async for event in self.app.astream(initial_state, config={"recursion_limit": self.recursion_limit}):
            for node_name, node_state in event.items():
                yield f"Finished node: {node_name}\n"
