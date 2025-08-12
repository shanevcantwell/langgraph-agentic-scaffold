# src/specialists/web_builder.py

import logging
import os
from typing import Dict, Any

from .base import BaseSpecialist
from ..graph.state import GraphState
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    """
    A specialist that generates Mermaid.js code from a high-level goal.
    """
    def __init__(self, llm_provider: str):
        # Load the system prompt from the dedicated file for better separation of concerns.
        prompt_path = os.path.join(os.path.dirname(__file__), "../../prompts/web_builder_prompt.md")
        with open(prompt_path, 'r') as f:
            system_prompt = f.read()

        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Generates the HTML artifact from the JSON artifact and updates the state.
        """
        logger.info("WEB BUILDER: Generating HTML Artifact")

        json_artifact = state.get("json_artifact", "{}") # Get the JSON artifact from the state

        # Prepare messages for the LLM, including the JSON artifact
        # The prompt for WebBuilder will instruct the LLM to convert this JSON into HTML
        messages_for_llm = state["messages"] + [HumanMessage(content=f"Visualize the following JSON object as an HTML document: {json_artifact}")]

        # 1. Invoke the LLM client directly with the prepared messages.
        ai_response = self.llm_client.invoke(messages_for_llm)

        # Wrap the AI response in the format expected by the graph state and _parse_llm_response.
        llm_response_dict = {"messages": [ai_response]}

        # 2. Use the robust parser from the base class to safely extract the string content.
        html_artifact = self._parse_llm_response(llm_response_dict)

        if not html_artifact:
            # This is a safeguard in case the LLM response was empty or malformed.
            logger.warning("WEB BUILDER: FAILED to parse LLM response.")
            html_artifact = "<html><body><h1>Error: Failed to generate HTML.</h1></body></html>" # Fallback HTML


        logger.info(f"WEB BUILDER: Generated HTML Artifact\n{html_artifact[:250]}...")

        # 3. Prepare the final dictionary to update the graph's state.
        # We take the original response dictionary (which contains the new message for the history)
        # and add the 'html_artifact' key to it.
        final_state_update = llm_response_dict.copy()
        final_state_update["html_artifact"] = html_artifact

        return final_state_update