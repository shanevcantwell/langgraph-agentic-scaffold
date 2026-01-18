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


# Generic inference interface (ADR-CORE-020)
class InferenceResponse(BaseModel):
    """Generic output for the infer() method - the 'just think about it' capability."""
    judgment: str = Field(..., description="The direct answer to the question (e.g., 'Paris', 'yes', 'finance') - NOT a label like 'Answer'")
    reasoning: str = Field(..., description="Step-by-step explanation of how you arrived at the judgment")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")


class InferenceService:
    """
    MCP Service for semantic judgment.

    Provides pure reasoning capabilities without tools or side effects.
    Callable from any specialist via MCP.

    Usage pattern (ADR-CORE-020): Specialists pass their own adapter at call time.
    This avoids the config gap where MCP services can't get dedicated bindings.

    Example:
        inference = InferenceService()
        result = inference.infer(
            context="...",
            question="Is this relevant?",
            llm_adapter=self.llm_adapter  # Specialist's adapter
        )
    """

    def __init__(self, llm_adapter: Optional[BaseAdapter] = None):
        self.llm_adapter = llm_adapter
        logger.info("InferenceService initialized" + (" with LLM adapter" if llm_adapter else " (adapter will be provided at call time)"))

    def get_mcp_functions(self) -> Dict[str, Any]:
        return {
            "infer": self.infer,  # Generic interface (ADR-CORE-020)
            "judge_relevance": self.judge_relevance,
            "detect_contradiction": self.detect_contradiction,
            "assess_source_quality": self.assess_source_quality
        }

    def infer(
        self,
        context: str,
        question: str,
        output_format: Optional[str] = None,
        llm_adapter: Optional[BaseAdapter] = None,
    ) -> Dict[str, Any]:
        """
        Generic semantic inference - the 'just think about it' capability.

        This is the escape hatch for when the right tool is no tool.
        Pass context and a question, get back a judgment with reasoning.

        Args:
            context: The raw text or data to analyze
            question: The specific judgment or inference to make
            output_format: Optional hint for response format ('boolean', 'category', 'json')
            llm_adapter: Optional adapter to use (defaults to instance adapter)

        Returns:
            Dict with 'judgment', 'reasoning', and 'confidence' keys

        Raises:
            ValueError: If no adapter provided and no instance adapter set
        """
        adapter = llm_adapter or self.llm_adapter
        if not adapter:
            raise ValueError("No LLM adapter provided. Pass llm_adapter parameter or set at init.")

        # Build format hint if provided
        format_hint = ""
        if output_format:
            if output_format == "boolean":
                format_hint = "\nYour judgment should be 'yes' or 'no'."
            elif output_format == "category":
                format_hint = "\nYour judgment should be one of the categories mentioned in the question."
            elif output_format == "json":
                format_hint = "\nYour judgment should be a JSON object if the question implies structure."

        prompt = f"""Answer the question using ONLY the context provided.

Context:
{context[:4000]}

Question: {question}
{format_hint}
Put your direct answer in "judgment" (just the answer itself, like "Paris" or "yes" - no prefix like "Answer:").
Put your step-by-step reasoning in "reasoning".
Put your confidence (0.0-1.0) in "confidence"."""

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=InferenceResponse
        )

        response = adapter.invoke(request)
        return response.get("json_response", {})

    def judge_relevance(
        self,
        query: str,
        content: str,
        llm_adapter: Optional[BaseAdapter] = None,
    ) -> Dict[str, Any]:
        """
        Determines if the content is relevant to the query.

        Args:
            query: The search query or topic
            content: The content to evaluate for relevance
            llm_adapter: Optional adapter to use (defaults to instance adapter)

        Returns:
            Dict with 'is_relevant', 'reasoning', and 'confidence' keys

        Raises:
            ValueError: If no adapter provided and no instance adapter set
        """
        adapter = llm_adapter or self.llm_adapter
        if not adapter:
            raise ValueError("No LLM adapter provided. Pass llm_adapter parameter or set at init.")

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

        response = adapter.invoke(request)
        return response.get("json_response", {})

    def detect_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        llm_adapter: Optional[BaseAdapter] = None,
    ) -> Dict[str, Any]:
        """
        Detects if two claims contradict each other.

        Args:
            claim_a: First claim to compare
            claim_b: Second claim to compare
            llm_adapter: Optional adapter to use (defaults to instance adapter)

        Returns:
            Dict with 'has_contradiction', 'explanation', and 'severity' keys

        Raises:
            ValueError: If no adapter provided and no instance adapter set
        """
        adapter = llm_adapter or self.llm_adapter
        if not adapter:
            raise ValueError("No LLM adapter provided. Pass llm_adapter parameter or set at init.")

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

        response = adapter.invoke(request)
        return response.get("json_response", {})

    def assess_source_quality(
        self,
        url: str,
        content: str,
        llm_adapter: Optional[BaseAdapter] = None,
    ) -> Dict[str, Any]:
        """
        Assesses the quality and reliability of a source.

        Args:
            url: The source URL
            content: Content snippet from the source
            llm_adapter: Optional adapter to use (defaults to instance adapter)

        Returns:
            Dict with 'reliability_score', 'bias_detected', and 'assessment' keys

        Raises:
            ValueError: If no adapter provided and no instance adapter set
        """
        adapter = llm_adapter or self.llm_adapter
        if not adapter:
            raise ValueError("No LLM adapter provided. Pass llm_adapter parameter or set at init.")

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

        response = adapter.invoke(request)
        return response.get("json_response", {})
