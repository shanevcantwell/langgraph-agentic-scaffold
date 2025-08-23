# app/src/specialists/wrapped_specialist.py

import importlib.util
import logging
import os
from .base import BaseSpecialist
from ..utils.path_utils import PROJECT_ROOT

logger = logging.getLogger(__name__)

class WrappedSpecialist(BaseSpecialist):
    """A specialist that wraps an externally-sourced agent."""

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)
        self.is_enabled = False
        self.external_agent = None

        source = self.specialist_config.get("source")        
        class_name = self.specialist_config.get("class_name")

        if not source or not class_name:
            logger.warning(f"Wrapped specialist '{specialist_name}' is disabled: missing 'source' or 'class_name' key in config.yaml.")
            return
        
        # Resolve the source path relative to the project root to make it robust.
        source_path = PROJECT_ROOT / source

        if not source_path.exists():
            logger.warning(f"Wrapped specialist '{specialist_name}' is disabled: source file not found at '{source_path}'.")
            logger.warning(f"Please ensure you have cloned the external agent into the correct directory as per the documentation.")
            return

        # The external agent is loaded once during initialization.
        try:
            self.external_agent = self._load_external_agent(str(source_path))
            self.is_enabled = True
            logger.info(f"Successfully loaded external agent for wrapped specialist '{specialist_name}'.")
        except Exception as e:
            logger.error(f"Failed to load external agent for '{specialist_name}' from '{source_path}': {e}", exc_info=True)

    def _load_external_agent(self, source: str):
        """Loads the external agent from the given source path."""
        class_name = self.specialist_config.get("class_name")
        if not class_name:
            # This case is now handled by the __init__ check, but as a safeguard:
            raise ValueError("Cannot load external agent: 'class_name' is missing from configuration.")
        spec = importlib.util.spec_from_file_location("external_agent", source)
        if spec is None:
            raise ImportError(f"Could not create module spec from source: {source}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, class_name):
            raise AttributeError(f"External agent module from '{source}' does not have a class named '{class_name}'.")

        AgentClass = getattr(module, class_name)
        return AgentClass()

    def _execute_logic(self, state: dict) -> dict:
        """Executes the wrapped external agent."""
        if not self.is_enabled:
            error_message = f"'{self.specialist_name}' is not enabled. Check server logs for configuration errors."
            logger.error(error_message)
            # Return an error in the state so the graph can handle it gracefully.
            return {"error": error_message}

        # 1. Translate the GraphState to the external agent's input format.
        external_agent_input = self._translate_state_to_input(state)

        # 2. Execute the external agent.
        external_agent_output = self.external_agent.run(external_agent_input)

        # 3. Translate the external agent's output back to the GraphState format.
        updated_state = self._translate_output_to_state(state, external_agent_output)

        return updated_state

    def _translate_state_to_input(self, state: dict) -> any:
        """Translates the GraphState to the external agent's input format."""
        # This method needs to be implemented by the specific wrapper specialist.
        raise NotImplementedError

    def _translate_output_to_state(self, state: dict, output: any) -> dict:
        """Translates the external agent's output back to the GraphState format."""
        # This method needs to be implemented by the specific wrapper specialist.
        raise NotImplementedError
