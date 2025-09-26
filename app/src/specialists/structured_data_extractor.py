# app/src/specialists/extractor_specialist.py
import logging
from typing import Dict, Any, Type
from pydantic import BaseModel

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class StructuredDataExtractor(BaseSpecialist):
    """
    A specialist that extracts structured data from text using a provided Pydantic model.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise RuntimeError("StructuredDataExtractor requires an LLM adapter.")

        messages = state.get("messages", [])
        scratchpad = state.get("scratchpad", {})
        
        pydantic_schema: Type[BaseModel] = scratchpad.get("extraction_schema")
        target_artifact_name: str = scratchpad.get("target_artifact_name")
        
        if not pydantic_schema or not target_artifact_name:
            error_message = "State missing 'extraction_schema' or 'target_artifact_name' in scratchpad."
            return {"messages": [create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=error_message
            )]}

        if not isinstance(pydantic_schema, type) or not issubclass(pydantic_schema, BaseModel):
            error_message = f"Invalid 'extraction_schema' provided in scratchpad. Expected a Pydantic model class, but got {type(pydantic_schema).__name__}."
            return {"messages": [create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=error_message
            )]}

        # Use the system LLM to generate a structured plan (the data object).
        # We pass the schema as a tool and force the LLM to use it.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[pydantic_schema],
            force_tool_call=True
        )
        response = self.llm_adapter.invoke(request)
        
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            fallback_msg = f"I was unable to extract the required '{pydantic_schema.__name__}' data."
            return {"messages": [create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=fallback_msg
            )]}

        try:
            # The "execution" is simply validating and returning the structured data.
            extracted_data = pydantic_schema(**tool_calls[0]['args'])
        except Exception as e:
            error_message = f"LLM tool call arguments failed Pydantic validation for schema '{pydantic_schema.__name__}'. Error: {e}"
            return {"messages": [create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=error_message
            )]}

        success_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"Successfully extracted '{pydantic_schema.__name__}' data and saved it to the '{target_artifact_name}' artifact."
        )
        
        return {
            "messages": [success_message],
            "extracted_data": extracted_data.model_dump(),
            "task_is_complete": True,
            "scratchpad": { # Clean up the scratchpad after use
                "extraction_schema": None,
                "target_artifact_name": None
            }
        }
