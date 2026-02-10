# app/src/specialists/data_processor_specialist.py
#
# DEPRECATED: Absorbed by text_analysis_specialist (Phase 1b).
# The "add processed_by stamp" behavior was trivial and doesn't
# warrant a separate specialist. text_analysis handles data
# transformation via ReAct tools (it-tools MCP, terminal).
# Removed from config.yaml routing.
#
import logging
import json
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

class DataProcessorSpecialist(BaseSpecialist):
    """
    DEPRECATED: Absorbed by TextAnalysisSpecialist.

    Was: Procedural specialist that adds 'processed_by' stamp to JSON.
    Now: text_analysis_specialist handles data operations via ReAct tools.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        json_artifact = state.get("json_artifact")
        if json_artifact is None:
            # This specialist is procedural and cannot self-correct with an LLM.
            # It returns a simple error message.
            return {"messages": [AIMessage(content="State is missing the required 'json_artifact' key.")]}
        if isinstance(json_artifact, str):
            data = json.loads(json_artifact)
        else:
            data = json_artifact

        # Perform some processing. For this example, we'll just add a key.
        data['processed_by'] = self.specialist_name

        new_message = AIMessage(content="I have processed the data artifact.")
        return {
            "messages": [new_message],
            "processed_data": data
        }