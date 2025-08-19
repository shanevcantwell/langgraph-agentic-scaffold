import logging
import json
import re
from typing import Dict, Any

from .base import BaseSpecialist
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class DataProcessorSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__(specialist_name="data_processor_specialist")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        logger.debug(f"DataProcessor: Received state: {state}")
        logger.info("---DATA PROCESSOR: Extracting JSON Artifact---")
        messages = state.get("messages", [])
        if not messages:
            error_message = "DataProcessor Error: No messages found in state to process."
            logger.error(error_message)
            return {"error": error_message}

        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            error_message = "DataProcessor Error: Last message is not a HumanMessage."
            logger.error(error_message)
            return {"error": error_message}

        user_input = last_message.content
        json_artifact = None

        try:
            # Attempt to find a JSON object in the user input
            # This regex is a basic attempt to find a JSON object.
            # More robust parsing might be needed for complex cases.
            json_match = re.search(r'\{.*\}', user_input, re.DOTALL)
            if json_match:
                extracted_json_str = json_match.group(0)
                # Validate that it's valid JSON
                json.loads(extracted_json_str)
                json_artifact = extracted_json_str
                logger.info("Successfully extracted JSON artifact from HumanMessage.")
            else:
                logger.warning("No JSON object found in the user's request.")
                json_artifact = "{}" # Return empty JSON if nothing found

        except json.JSONDecodeError as e:
            error_message = f"DataProcessor Error: Failed to decode JSON from user input: {e}"
            logger.error(error_message)
            return {"error": error_message}
        except Exception as e:
            error_message = f"An unexpected error occurred in DataProcessorSpecialist: {e}"
            logger.error(error_message)
            return {"error": error_message}

        # After extracting the JSON, the next step is to route to the web_builder
        # This assumes a direct flow from data processing to web building.
        # In a more complex system, another routing step might be needed.
        return_value = {
            "json_artifact": json_artifact,
            "next_specialist": "web_builder",
            "error": None
        }
        logger.debug(f"DataProcessor: Returning: {return_value}")
        return return_value