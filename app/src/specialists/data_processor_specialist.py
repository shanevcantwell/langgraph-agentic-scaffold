import logging
import json
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

class DataProcessorSpecialist(BaseSpecialist):
    """
    A procedural (LLM-optional) specialist that processes a JSON artifact
    found in the state.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        json_artifact = state.get("json_artifact")
        if isinstance(json_artifact, str):
            data = json.loads(json_artifact)
        else:
            data = json_artifact

        # Perform some processing. For this example, we'll just add a key.
        data['processed_by'] = self.specialist_name

        new_message = AIMessage(content="I have processed the data artifact.")
        return {
            "messages": state["messages"] + [new_message],
            "processed_data": data
        }