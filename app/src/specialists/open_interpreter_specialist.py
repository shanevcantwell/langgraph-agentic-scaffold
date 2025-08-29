# app/src/specialists/open_interpreter_specialist.py

import logging
from typing import Dict, Any, Optional

from interpreter import interpreter
from langchain_core.messages import AIMessage

from .base import BaseSpecialist

logger = logging.getLogger(__name__)


class OpenInterpreterSpecialist(BaseSpecialist):
    """
    A procedural specialist that uses the open-interpreter library to execute code.
    It is configured via the `external_llm_provider_binding` in config.yaml.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        # The specialist_config will be injected by the ChiefOfStaff after initialization.
        # We use a property setter to trigger configuration when the config is assigned.
        self._specialist_config: Optional[Dict[str, Any]] = None
        # This will be injected by the ChiefOfStaff before specialist_config is set.
        self.external_provider_config: Optional[Dict[str, Any]] = None

    @property
    def specialist_config(self) -> Optional[Dict[str, Any]]:
        """Gets the specialist configuration."""
        return self._specialist_config

    @specialist_config.setter
    def specialist_config(self, config: Dict[str, Any]):
        """
        Sets the specialist configuration and triggers the interpreter setup.
        This method is called by the ChiefOfStaff during its loading process.
        """
        self._specialist_config = config
        self._configure_interpreter()
        logger.info("---INITIALIZED OpenInterpreterSpecialist---")

    def _configure_interpreter(self):
        """Configures the open-interpreter singleton based on the specialist's config."""
        if not self.specialist_config:
            logger.warning("Cannot configure OpenInterpreter: specialist_config is not set.")
            return

        binding_key = self.specialist_config.get("external_llm_provider_binding")
        if not self.external_provider_config:
            # This case should be prevented by the ChiefOfStaff's loading logic.
            raise ValueError(
                f"OpenInterpreterSpecialist has binding '{binding_key}' but "
                "its external_provider_config was not injected."
            )
        
        provider_config = self.external_provider_config

        # Configure interpreter based on provider type
        interpreter.auto_run = True
        interpreter.model = provider_config.get("api_identifier")
        
        provider_type = provider_config.get("type")
        if provider_type == "lmstudio" or provider_type == "ollama":
            interpreter.api_base = provider_config.get("base_url")
            interpreter.api_key = "lm-studio"  # Can be any non-empty string
        elif provider_type == "gemini":
            interpreter.api_key = provider_config.get("api_key")
        
        interpreter.system_message = (
            "You are Open Interpreter, a world-class programmer that can complete any task by executing code. "
            "You are in a sandboxed environment. You can only read/write files in the './workspace' directory. "
            "When you are done, respond with a summary of what you have done."
        )
        logger.info(f"OpenInterpreter configured to use LLM provider: {binding_key}")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.specialist_config:
            raise RuntimeError("OpenInterpreterSpecialist cannot execute without being configured.")

        last_message = state["messages"][-1].content
        interpreter.messages = []
        logger.info(f"Executing prompt with Open Interpreter: {last_message[:100]}...")
        response_messages = interpreter.chat(last_message, display=False, stream=False)
        assistant_responses = [m['content'] for m in response_messages if m['role'] == 'assistant']
        final_output = "\n".join(assistant_responses) if assistant_responses else "Task completed with no output."
        logger.info(f"Open Interpreter finished execution. Output: {final_output[:200]}...")
        ai_message = AIMessage(content=final_output, name=self.specialist_name)
        return {"messages": [ai_message]}