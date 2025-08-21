
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from ..graph.state import GraphState

logger = logging.getLogger(__name__)

class ArchiverSpecialist(BaseSpecialist):
    """
    The Archiver Specialist is responsible for summarizing the conversation
    and preparing the final report. It's the last step in the workflow.
    """
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)

    def _execute_logic(self, state: GraphState) -> Dict[str, Any]:
        logger.info("---Executing Archiver Specialist---")

        messages = state.get("messages", [])
        summary = "Conversation summary:\n"
        for msg in messages:
            summary += f"- {msg.type}: {msg.content}\n"

        # In a real implementation, this would be a more sophisticated summary.
        # For now, we just join the messages.

        report = f"# Archive Report\n\n{summary}"

        logger.info("Successfully generated archive report.")

        return {
            "archive_report": report,
            "next_specialist": "__FINISH__" # Signal to end the graph
        }
