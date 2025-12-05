import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from ...llm.adapter import BaseAdapter, StandardizedLLMRequest

logger = logging.getLogger(__name__)

class RelevanceJudgment(BaseModel):
    is_relevant: bool = Field(..., description="Whether the content is relevant to the query")
    reasoning: str = Field(..., description="Brief explanation of the judgment")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")

class ContradictionAnalysis(BaseModel):
    has_contradiction: bool = Field(..., description="Whether a contradiction exists")
    explanation: str = Field(..., description="Explanation of the contradiction or agreement")
    severity: str = Field(..., description="Severity of contradiction: 'none', 'minor', 'major'")

class QualityAssessment(BaseModel):
    reliability_score: float = Field(..., description="Reliability score between 0.0 and 1.0")
    bias_detected: bool = Field(..., description="Whether significant bias is detected")
    assessment: str = Field(..., description="Qualitative assessment of the source")

class InferenceService:
    """
    MCP Service for semantic judgment.
    
    Provides pure reasoning capabilities without tools or side effects.
    Callable from any specialist via MCP.
    """
    
    def __init__(self, llm_adapter: BaseAdapter):
        self.llm_adapter = llm_adapter
        logger.info("InferenceService initialized with LLM adapter")

    def get_mcp_functions(self) -> Dict[str, Any]:
        return {
            "judge_relevance": self.judge_relevance,
            "detect_contradiction": self.detect_contradiction,
            "assess_source_quality": self.assess_source_quality
        }

    def judge_relevance(self, query: str, content: str) -> Dict[str, Any]:
        """
        Determines if the content is relevant to the query.
        """
        prompt = f"""
        Task: Judge the relevance of the following content to the query.
        
        Query: {query}
        
        Content:
        {content[:2000]}  # Truncate to avoid context overflow
        
        Return a JSON object with:
        - is_relevant: boolean
        - reasoning: string
        - confidence: float (0.0 to 1.0)
        """
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=RelevanceJudgment
        )
        
        response = self.llm_adapter.invoke(request)
        return response.get("structured_output", {})

    def detect_contradiction(self, claim_a: str, claim_b: str) -> Dict[str, Any]:
        """
        Detects if two claims contradict each other.
        """
        prompt = f"""
        Task: Analyze if the following two claims contradict each other.
        
        Claim A: {claim_a}
        
        Claim B: {claim_b}
        
        Return a JSON object with:
        - has_contradiction: boolean
        - explanation: string
        - severity: 'none', 'minor', 'major'
        """
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=ContradictionAnalysis
        )
        
        response = self.llm_adapter.invoke(request)
        return response.get("structured_output", {})

    def assess_source_quality(self, url: str, content: str) -> Dict[str, Any]:
        """
        Assesses the quality and reliability of a source.
        """
        prompt = f"""
        Task: Assess the quality and reliability of the following source.
        
        URL: {url}
        
        Content Snippet:
        {content[:1000]}
        
        Return a JSON object with:
        - reliability_score: float (0.0 to 1.0)
        - bias_detected: boolean
        - assessment: string
        """
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=QualityAssessment
        )
        
        response = self.llm_adapter.invoke(request)
        return response.get("structured_output", {})
