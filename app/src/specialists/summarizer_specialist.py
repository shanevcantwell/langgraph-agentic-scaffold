import logging
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class SummarizerSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

    def register_mcp_services(self, registry):
        """Expose summarization capability via MCP."""
        registry.register_service(self.specialist_name, {
            "summarize": self._summarize
        })

    def _summarize(self, text: str, max_length: int = 1000) -> str:
        """
        Summarizes the provided text using the attached LLM.
        """
        if not self.llm_adapter:
            raise ValueError(f"LLM Adapter not attached to {self.specialist_name}")

        logger.info(f"Summarizer processing text of length {len(text)}")
        
        # Load system prompt if available
        prompt_file = self.specialist_config.get("prompt_file")
        system_prompt = ""
        if prompt_file:
            try:
                system_prompt = load_prompt(prompt_file)
            except Exception:
                pass
        
        user_prompt = f"Please summarize the following text. Keep the summary concise (under {max_length} characters) but retain key information:\n\n{text}"
        
        messages = []
        if system_prompt:
            # We can't easily add SystemMessage here if we want to keep it simple, 
            # but StandardizedLLMRequest handles it if we pass it.
            # Actually, the adapter might already have the system prompt baked in if configured that way.
            # But for MCP calls, we might want to override or augment.
            # Let's just use the user prompt for the specific task.
            pass
            
        request = StandardizedLLMRequest(messages=[HumanMessage(content=user_prompt)])
        response = self.llm_adapter.invoke(request)
        return response.get("text_response", "")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Graph execution mode: Summarizes 'text_to_process' artifact.
        """
        artifacts = state.get("artifacts", {})
        text = artifacts.get("text_to_process")
        
        if not text:
            logger.warning("Summarizer: No 'text_to_process' artifact found.")
            return {"error": "No text to process."}
            
        summary = self._summarize(text)
        
        return {
            "artifacts": {
                "summary": summary
            },
            "scratchpad": {
                "summary_generated": True
            }
        }
