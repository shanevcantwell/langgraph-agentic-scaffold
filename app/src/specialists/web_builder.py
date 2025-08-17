import logging
import json
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt
from ..llm.clients import LLMInvocationError

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    def __init__(self, llm_provider: str):
        system_prompt = load_prompt("web_builder")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        logger.info("---WEB BUILDER: Generating HTML Artifact---")
        try:
            json_artifact = state.get("json_artifact")
            if not json_artifact:
                return {"error": "WebBuilder Error: Input 'json_artifact' not found in state."}

            messages = [
                SystemMessage(content=self.system_prompt_content),
                HumanMessage(content=f"Here is the JSON data to visualize:\n\n{json_artifact}")
            ]
            
            parsed_json = self.llm_client.invoke(messages)
            
            html_document = parsed_json.get("html_document")
            if not html_document:
                # This now catches a valid JSON response that doesn't match our schema
                raise KeyError("LLM response is valid JSON but is missing the 'html_document' key.")

            logger.info("Successfully generated HTML artifact.")
            return {"html_artifact": html_document, "error": None}

        except LLMInvocationError as e:
            error_message = f"Web Builder failed due to LLM error: {e}"
            logger.error(error_message)
            return {"error": error_message}
        except KeyError as e:
            error_message = f"WebBuilder contract error: {e}"
            logger.error(error_message)
            logger.debug(f"Non-compliant JSON received from LLM: {parsed_json}")
            return {"error": error_message}
        except Exception as e:
            error_message = f"An unexpected error occurred in WebBuilder: {e}"
            logger.error(error_message)
            return {"error": error_message}
