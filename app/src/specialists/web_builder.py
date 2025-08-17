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

        # 1. Get the JSON artifact from the state.
        json_artifact = state.get("json_artifact")
        if not json_artifact:
            error_message = "WEB BUILDER: 'json_artifact' not found in state. Cannot generate HTML."
            logger.error(error_message)
            return {"error": "Missing Dependency", "error_details": error_message}

        # 2. Create a specific prompt for the Web Builder to convert the JSON to HTML.
        user_prompt = f"""Based on the following JSON artifact, create a complete HTML document that renders the diagram using Mermaid.js.
The HTML must include the necessary Mermaid.js library script tag and the Mermaid diagram definition within a `<pre class="mermaid">` tag.

JSON Artifact:
```json
{json_artifact}
```"""

        # 3. Invoke the LLM with the specific, focused prompt.
        llm_input = {"messages": [HumanMessage(content=user_prompt)]}
        llm_response_dict = self.invoke(llm_input)

        # 4. Check for errors from the LLM client.
        if "error" in llm_response_dict:
            logger.error(f"Web Builder failed to get a valid response from the LLM. Error: {llm_response_dict['error']}")
            return llm_response_dict

        # 5. Use the robust parser from the base class to safely extract the string content.
        html_artifact = self._parse_llm_response(llm_response_dict)

        if not html_artifact:
            logger.warning("WEB BUILDER: FAILED to parse LLM response.")
            return {"error": "LLM Parsing Failed", "error_details": "Web Builder failed to parse a valid HTML artifact from the LLM response."}

        logger.info(f"WEB BUILDER: Generated HTML Artifact\n{html_artifact[:250]}...")

        # 6. Prepare the final dictionary to update the graph's state.
        final_state_update = llm_response_dict.copy()
        final_state_update["html_artifact"] = html_artifact

        return final_state_update
