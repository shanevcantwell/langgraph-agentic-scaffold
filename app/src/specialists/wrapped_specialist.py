# app/src/specialists/wrapped_specialist.py

import importlib.util
from .base import BaseSpecialist

class WrappedSpecialist(BaseSpecialist):
    """A specialist that wraps an externally-sourced agent."""

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)
        source = self.specialist_config.get("source")
        if not source:
            raise ValueError(f"Wrapped specialist '{specialist_name}' is missing the 'source' key in its config.yaml entry.")
        # The external agent is loaded once during initialization.
        self.external_agent = self._load_external_agent(source)

    def _load_external_agent(self, source: str):
        """Loads the external agent from the given source path."""
        spec = importlib.util.spec_from_file_location("external_agent", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Assuming the external agent has a class named 'Agent'
        return module.Agent()

    def _execute_logic(self, state: dict) -> dict:
        """Executes the wrapped external agent."""
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
