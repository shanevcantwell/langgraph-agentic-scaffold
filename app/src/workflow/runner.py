# src/workflow/runner.py
import logging
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.messages import messages_to_dict
from pydantic import BaseModel

from ..utils.errors import ConfigError
from ..graph.state import GraphState
from .graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


def _make_state_serializable(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively traverses a state dictionary and converts non-serializable
    objects (like LangChain messages, Pydantic models, and datetimes)
    into JSON-compatible formats.
    """
    if isinstance(state, dict):
        new_dict = {}
        for k, v in state.items():
            new_dict[k] = _make_state_serializable(v)
        return new_dict
    elif isinstance(state, list):
        if state and isinstance(state[0], BaseMessage):
            return messages_to_dict(state)
        return [_make_state_serializable(item) for item in state]
    elif isinstance(state, BaseModel):
        return state.model_dump()
    elif isinstance(state, datetime):
        return state.isoformat()
    return state


class WorkflowRunner:
    """
    A service class that encapsulates the logic for running the agentic workflow.
    This acts as a Facade, providing a simple interface to the complex internal system.
    """
    def __init__(self):
        """
        Initializes the WorkflowRunner by instantiating the GraphBuilder
        and compiling the LangGraph application.
        """
        self.builder = GraphBuilder()
        self.config = self.builder.config
        self.specialists = self.builder.specialists
        self._perform_pre_flight_checks()
        self.recursion_limit = self.config.get("workflow", {}).get("recursion_limit", 25)
        self.app = self.builder.build()
        logger.info("WorkflowRunner initialized with compiled graph.")

    def _perform_pre_flight_checks(self):
        """
        Performs critical environment checks before the application is fully wired.
        This ensures the system fails fast if essential configurations are missing.
        """
        logger.info("Performing pre-flight environment checks...")
        llm_providers = self.config.get("llm_providers", {})
        
        # Build a comprehensive set of all provider bindings that are actually in use.
        used_provider_bindings = set()
        # 1. Check bindings on individual specialists
        for spec_config in self.config.get("specialists", {}).values():
            if binding := spec_config.get("llm_config"):
                used_provider_bindings.add(binding)
        # 2. Check the default binding
        if default_binding := self.config.get("workflow", {}).get("default_llm_config"):
            used_provider_bindings.add(default_binding)

        if not used_provider_bindings:
            logger.warning("Pre-flight check: No LLM providers appear to be in use.")

        for binding_key, provider_config in llm_providers.items():
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

        workflow_config = self.config.get("workflow", {})
        critical_specialists = workflow_config.get("critical_specialists", [])
        if critical_specialists:
            loaded_specialist_names = self.specialists.keys()
            missing_critical = [name for name in critical_specialists if name not in loaded_specialist_names]
            if missing_critical:
                raise ConfigError(
                    f"Pre-flight check failed: The following critical specialists failed to load: {missing_critical}. "
                    "The application cannot start in this state. Please check the logs for errors related to these specialists."
                )
            logger.info(f"Successfully validated that all critical specialists are loaded: {critical_specialists}")

        logger.info("All pre-flight checks passed successfully.")

    def run(self, goal: str, text_to_process: str = None, image_to_process: str = None) -> Dict[str, Any]:
        """
        Executes the workflow with a given goal.
        """
        logger.info(f"--- Starting workflow for goal: '{goal}' ---")

        initial_state: GraphState = {
            "messages": [HumanMessage(content=goal, name="user")],
            "routing_history": [], "turn_count": 0, "task_is_complete": False, "next_specialist": None,
            "artifacts": {}, "scratchpad": {}, "recommended_specialists": None, "error_report": None
        }
        if image_to_process:
            initial_state["artifacts"]["uploaded_image.png"] = image_to_process
        if text_to_process:
            initial_state["artifacts"]["text_to_process"] = text_to_process

        try:
            final_state = self.app.invoke(initial_state, config={"recursion_limit": self.recursion_limit})
            logger.info("--- Workflow completed successfully ---")

            final_artifacts = final_state.get("artifacts", {})
            final_response = final_artifacts.get("final_user_response.md", "Workflow completed, but no final user response was generated.")
            
            return {"final_user_response": final_response}

        except Exception as e:
            logger.error(f"--- Workflow failed with an unhandled exception: {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed catastrophically: {e}",
                "messages": [HumanMessage(content=goal)], "turn_count": 0,
            }

    async def run_streaming(self, goal: str, text_to_process: str = None, image_to_process: str = None) -> AsyncGenerator[str, None]:
        """
        Executes the workflow with a given goal and streams back real-time updates.
        """
        logger.info(f"--- Starting streaming workflow for goal: '{goal}' ---")

        initial_state: GraphState = {
            "messages": [HumanMessage(content=goal, name="user")],
            "routing_history": [], "turn_count": 0, "task_is_complete": False, "next_specialist": None,
            "artifacts": {}, "scratchpad": {}, "recommended_specialists": None, "error_report": None
        }
        if image_to_process:
             initial_state["artifacts"]["uploaded_image.png"] = image_to_process
        if text_to_process:
            initial_state["artifacts"]["text_to_process"] = text_to_process

        final_state = None
        try:
            async for event in self.app.astream(initial_state, config={"recursion_limit": self.recursion_limit}):
                for node_name, node_state in event.items():
                    final_state = node_state
                    yield f"Finished node: {node_name}\n"

            if final_state:
                
                serializable_state = _make_state_serializable(final_state)
                final_state_json = json.dumps(serializable_state, indent=2)
                yield f"FINAL_STATE::{final_state_json}"
                logger.info("--- Streaming workflow complete. Sent final state to client. ---")
            else:
                logger.error("--- Streaming workflow finished but no final state was captured. ---")
        
        except Exception as e:
            logger.error(f"--- Streaming workflow failed with an unhandled exception: {e} ---", exc_info=True)
            # Create a serializable error message
            error_message_dict = {"error": f"Workflow failed catastrophically: {str(e)}"}
            error_message_json = json.dumps(error_message_dict)
            yield f"FINAL_STATE::{error_message_json}"