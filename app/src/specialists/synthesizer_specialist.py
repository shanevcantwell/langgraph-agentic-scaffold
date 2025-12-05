import logging
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class SynthesizerSpecialist(BaseSpecialist):
    """
    Synthesizes research findings into a coherent report.
    """
    
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        scratchpad = state.get("scratchpad", {})
        research_goal = scratchpad.get("research_goal")
        research_results = scratchpad.get("research_results", [])
        
        if not research_goal:
            return {"error": "No research_goal provided"}
            
        if not research_results:
            return {"error": "No research_results provided"}
            
        logger.info(f"Synthesizing report for goal: {research_goal}")
        
        report = self._generate_report(research_goal, research_results)
        
        return {
            "research_report": report,
            "status": "completed"
        }

    def _generate_report(self, goal: str, results: List[Dict[str, Any]]) -> str:
        # Format results for the prompt
        results_text = ""
        for i, res in enumerate(results):
            results_text += f"Source {i+1}: {res.get('url')}\n"
            results_text += f"Content: {res.get('content')[:2000]}\n\n" # Truncate
            
        prompt = f"""
        Task: Synthesize the following research findings into a comprehensive report.
        
        Goal: {goal}
        
        Findings:
        {results_text}
        
        Report:
        """
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)]
        )
        
        response = self.llm_adapter.invoke(request)
        return response.get("content", "")
