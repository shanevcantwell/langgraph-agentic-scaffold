import logging
import json
from typing import Dict, Any

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    def __init__(self):
        super().__init__(specialist_name="web_builder")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        logger.info("---WEB BUILDER: Generating HTML Artifact---")
        json_artifact = state.get("json_artifact")
        if not json_artifact:
            return {"error": "WebBuilder Error: Input 'json_artifact' not found in state."}

        system_prompt = load_prompt("web_builder_prompt.md")

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=f"Here is the JSON data to visualize:\n\n{json_artifact}")],
            system_prompt_content=system_prompt,
            output_schema={"html_document": "<html>...</html>"}
        )

        try:
            response_data = self.llm_adapter.invoke(request)
            
            # If response_data is a string, attempt to parse it as JSON
            if isinstance(response_data, str):
                try:
                    response_data = json.loads(response_data)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to decode JSON from LLM response: {e}") from e

            html_document = response_data.get("html_document")
            if not html_document:
                raise KeyError("LLM response is valid JSON but is missing the 'html_document' key.")

            logger.info("Successfully generated HTML artifact.")
            return {"html_artifact": html_document, "error": None}
        except Exception as e:
            error_message = f"An unexpected error occurred in WebBuilder: {e}"
            logger.error(error_message)
            return {"error": error_message}
