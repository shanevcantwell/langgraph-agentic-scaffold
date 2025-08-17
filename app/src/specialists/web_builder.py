import logging
import json
import re
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    """
    A specialist that takes a JSON artifact from the state and generates a
    self-contained HTML document to visualize the data.
    """

    def __init__(self, llm_provider: str):
        """
        Initializes the WebBuilder specialist.

        Args:
            llm_provider: The provider for the language model.
        """
        system_prompt = load_prompt("web_builder")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Reads a JSON artifact from the state, invokes an LLM to create an HTML
        visualization, and updates the state with the HTML artifact or an error.

        Args:
            state: The current state of the graph.

        Returns:
            A dictionary to update the GraphState, containing either 'html_artifact'
            on success or 'error' on failure.
        """
        logger.info("---WEB BUILDER: Generating HTML Artifact---")
        response_content = "" # Initialize in case of early exit

        try:
            json_artifact = state.get("json_artifact")
            if not json_artifact:
                error_message = "WebBuilder Error: Input 'json_artifact' not found in state."
                logger.error(error_message)
                return {"error": error_message}

            messages = [
                SystemMessage(content=self.system_prompt_content),
                HumanMessage(content=f"Here is the JSON data to visualize:\n\n{json_artifact}")
            ]
            
            logger.info(f"Invoking LLM ({self.llm_client.model}) for HTML artifact generation.")
            llm_response = self.llm_client.invoke(messages)
            response_content = llm_response.content

            cleaned_content = re.sub(r"```(json)?\n(.*)\n```", r"\2", response_content, flags=re.DOTALL).strip()
            parsed_json = json.loads(cleaned_content)
            
            html_document = parsed_json.get("html_document")
            if not html_document:
                # MODIFIED: Raise a more specific error to log the invalid content.
                raise KeyError("LLM response is missing the 'html_document' key.")

            logger.info("Successfully generated HTML artifact.")
            return {"html_artifact": html_document, "error": None}

        except json.JSONDecodeError as e:
            error_message = f"WebBuilder Error: Failed to parse LLM response as JSON. Details: {e}"
            logger.error(error_message)
            logger.debug(f"Invalid content received: {response_content}")
            return {"error": error_message}
        
        except KeyError as e:
            # ADDED: Specific handling for the missing key to improve debuggability.
            error_message = f"WebBuilder Error: {e}"
            logger.error(error_message)
            logger.debug(f"Non-compliant JSON received: {response_content}")
            return {"error": error_message}

        except Exception as e:
            error_message = f"An unexpected error occurred in WebBuilder: {e}"
            logger.error(error_message)
            return {"error": error_message}