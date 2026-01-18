"""
Unit tests for InferenceService - Pure semantic judgment MCP service.

Tests validate the generic infer() method, format hints, and structured output.
Uses mocked LLM adapter for speed and determinism.
"""

import pytest
from unittest.mock import Mock, MagicMock

from app.src.mcp.services.inference_service import (
    InferenceService,
    InferenceResponse,
    RelevanceJudgment,
    ContradictionAnalysis,
    QualityAssessment,
)
from app.src.llm.adapter import BaseAdapter, StandardizedLLMRequest


class TestInferenceServiceInitialization:
    """Test suite for InferenceService initialization."""

    def test_service_initializes_with_adapter(self):
        """Test that service stores adapter reference when provided."""
        adapter = Mock(spec=BaseAdapter)
        service = InferenceService(llm_adapter=adapter)

        assert service.llm_adapter is adapter

    def test_service_initializes_without_adapter(self):
        """Test that service can be initialized without adapter (ADR-CORE-020)."""
        service = InferenceService()

        assert service.llm_adapter is None

    def test_get_mcp_functions_returns_all_methods(self):
        """Test that get_mcp_functions exposes all service methods."""
        adapter = Mock(spec=BaseAdapter)
        service = InferenceService(llm_adapter=adapter)

        functions = service.get_mcp_functions()

        assert "infer" in functions
        assert "judge_relevance" in functions
        assert "detect_contradiction" in functions
        assert "assess_source_quality" in functions
        assert len(functions) == 4


class TestInferMethod:
    """Test suite for the generic infer() method (ADR-CORE-020)."""

    def test_infer_returns_json_response(self):
        """Test that infer() returns judgment, reasoning, and confidence."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {
            "json_response": {
                "judgment": "yes",
                "reasoning": "The context clearly supports this conclusion.",
                "confidence": 0.95
            }
        }

        service = InferenceService(llm_adapter=adapter)
        result = service.infer(
            context="The sky is blue during clear days.",
            question="Is the sky blue?"
        )

        assert result["judgment"] == "yes"
        assert "reasoning" in result
        assert result["confidence"] == 0.95

    def test_infer_passes_context_to_llm(self):
        """Test that context is included in the LLM request."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Important context here.",
            question="What is the answer?"
        )

        # Verify invoke was called
        assert adapter.invoke.called
        request = adapter.invoke.call_args[0][0]

        # Verify request structure
        assert isinstance(request, StandardizedLLMRequest)
        assert "Important context here" in request.messages[0].content
        assert "What is the answer?" in request.messages[0].content

    def test_infer_truncates_long_context(self):
        """Test that context over 4000 chars is truncated."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        long_context = "x" * 5000

        service.infer(context=long_context, question="Question?")

        request = adapter.invoke.call_args[0][0]
        # Context should be truncated to 4000 chars
        assert len(long_context) == 5000
        # The prompt contains the truncated context
        assert "x" * 4000 in request.messages[0].content
        assert "x" * 4001 not in request.messages[0].content

    def test_infer_uses_inference_response_schema(self):
        """Test that infer() uses InferenceResponse as output model."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(context="ctx", question="q")

        request = adapter.invoke.call_args[0][0]
        assert request.output_model_class == InferenceResponse


class TestInferFormatHints:
    """Test suite for output_format hints in infer()."""

    def test_infer_boolean_format_hint(self):
        """Test that boolean format adds yes/no instruction."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Some context",
            question="Is this true?",
            output_format="boolean"
        )

        request = adapter.invoke.call_args[0][0]
        assert "yes" in request.messages[0].content.lower()
        assert "no" in request.messages[0].content.lower()

    def test_infer_category_format_hint(self):
        """Test that category format adds category instruction."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Document content",
            question="Is this finance, legal, or HR?",
            output_format="category"
        )

        request = adapter.invoke.call_args[0][0]
        assert "categories" in request.messages[0].content.lower()

    def test_infer_json_format_hint(self):
        """Test that json format adds JSON instruction."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Data",
            question="Extract the key fields",
            output_format="json"
        )

        request = adapter.invoke.call_args[0][0]
        assert "json" in request.messages[0].content.lower()

    def test_infer_no_format_hint_when_none(self):
        """Test that no format hint is added when output_format is None."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Context",
            question="Question?",
            output_format=None
        )

        request = adapter.invoke.call_args[0][0]
        # Should not contain format-specific instructions
        assert "Your judgment should be 'yes' or 'no'" not in request.messages[0].content
        assert "categories mentioned" not in request.messages[0].content


class TestInferenceResponseSchema:
    """Test suite for InferenceResponse Pydantic model."""

    def test_inference_response_validates_required_fields(self):
        """Test that InferenceResponse requires all fields."""
        response = InferenceResponse(
            judgment="The answer is X",
            reasoning="Because of Y and Z",
            confidence=0.85
        )

        assert response.judgment == "The answer is X"
        assert response.reasoning == "Because of Y and Z"
        assert response.confidence == 0.85

    def test_inference_response_confidence_is_float(self):
        """Test that confidence is stored as float."""
        response = InferenceResponse(
            judgment="yes",
            reasoning="Clear evidence",
            confidence=0.9
        )

        assert isinstance(response.confidence, float)


class TestExistingMethods:
    """Test suite for existing specific methods (judge_relevance, etc.)."""

    def test_judge_relevance_calls_adapter(self):
        """Test that judge_relevance invokes LLM adapter."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {
            "json_response": {
                "is_relevant": True,
                "reasoning": "Directly addresses the query",
                "confidence": 0.9
            }
        }

        service = InferenceService(llm_adapter=adapter)
        result = service.judge_relevance(
            query="Python frameworks",
            content="Django is a popular Python web framework."
        )

        assert adapter.invoke.called
        assert result["is_relevant"] is True

    def test_detect_contradiction_calls_adapter(self):
        """Test that detect_contradiction invokes LLM adapter."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {
            "json_response": {
                "has_contradiction": True,
                "explanation": "Claims are mutually exclusive",
                "severity": "major"
            }
        }

        service = InferenceService(llm_adapter=adapter)
        result = service.detect_contradiction(
            claim_a="The sky is blue",
            claim_b="The sky is green"
        )

        assert adapter.invoke.called
        assert result["has_contradiction"] is True
        assert result["severity"] == "major"

    def test_assess_source_quality_calls_adapter(self):
        """Test that assess_source_quality invokes LLM adapter."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {
            "json_response": {
                "reliability_score": 0.8,
                "bias_detected": False,
                "assessment": "Reputable source"
            }
        }

        service = InferenceService(llm_adapter=adapter)
        result = service.assess_source_quality(
            url="https://example.com/article",
            content="Well-researched article content..."
        )

        assert adapter.invoke.called
        assert result["reliability_score"] == 0.8
        assert result["bias_detected"] is False


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_infer_handles_empty_json_response(self):
        """Test that infer() handles missing json_response gracefully."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {}  # No json_response key

        service = InferenceService(llm_adapter=adapter)
        result = service.infer(context="ctx", question="q")

        assert result == {}

    def test_infer_handles_empty_context(self):
        """Test that infer() handles empty context."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {"judgment": "unknown"}}

        service = InferenceService(llm_adapter=adapter)
        result = service.infer(context="", question="What is this about?")

        assert adapter.invoke.called
        assert result["judgment"] == "unknown"

    def test_infer_handles_unknown_format(self):
        """Test that unknown output_format is ignored (no hint added)."""
        adapter = Mock(spec=BaseAdapter)
        adapter.invoke.return_value = {"json_response": {}}

        service = InferenceService(llm_adapter=adapter)
        service.infer(
            context="Context",
            question="Question?",
            output_format="unknown_format"
        )

        request = adapter.invoke.call_args[0][0]
        # Unknown format should not add any specific hint
        assert "Your judgment should be" not in request.messages[0].content


class TestCallTimeAdapterPattern:
    """Test suite for call-time adapter pattern (ADR-CORE-020).

    InferenceService supports passing adapter at call time, allowing specialists
    to use their own adapter rather than requiring a dedicated binding.
    """

    def test_infer_uses_call_time_adapter(self):
        """Test that infer() uses adapter passed at call time."""
        call_time_adapter = Mock(spec=BaseAdapter)
        call_time_adapter.invoke.return_value = {
            "json_response": {"judgment": "yes", "reasoning": "...", "confidence": 0.9}
        }

        service = InferenceService()  # No instance adapter
        result = service.infer(
            context="ctx",
            question="q",
            llm_adapter=call_time_adapter
        )

        assert call_time_adapter.invoke.called
        assert result["judgment"] == "yes"

    def test_infer_call_time_adapter_overrides_instance(self):
        """Test that call-time adapter takes precedence over instance adapter."""
        instance_adapter = Mock(spec=BaseAdapter)
        call_time_adapter = Mock(spec=BaseAdapter)
        call_time_adapter.invoke.return_value = {"json_response": {"judgment": "call_time"}}

        service = InferenceService(llm_adapter=instance_adapter)
        result = service.infer(
            context="ctx",
            question="q",
            llm_adapter=call_time_adapter
        )

        # Call-time adapter should be used, not instance adapter
        assert call_time_adapter.invoke.called
        assert not instance_adapter.invoke.called
        assert result["judgment"] == "call_time"

    def test_infer_raises_without_any_adapter(self):
        """Test that infer() raises ValueError when no adapter available."""
        service = InferenceService()  # No instance adapter

        with pytest.raises(ValueError, match="No LLM adapter provided"):
            service.infer(context="ctx", question="q")

    def test_judge_relevance_uses_call_time_adapter(self):
        """Test that judge_relevance() accepts call-time adapter."""
        call_time_adapter = Mock(spec=BaseAdapter)
        call_time_adapter.invoke.return_value = {
            "json_response": {"is_relevant": True, "reasoning": "...", "confidence": 0.9}
        }

        service = InferenceService()
        result = service.judge_relevance(
            query="test",
            content="content",
            llm_adapter=call_time_adapter
        )

        assert call_time_adapter.invoke.called
        assert result["is_relevant"] is True

    def test_judge_relevance_raises_without_adapter(self):
        """Test that judge_relevance() raises ValueError when no adapter."""
        service = InferenceService()

        with pytest.raises(ValueError, match="No LLM adapter provided"):
            service.judge_relevance(query="q", content="c")

    def test_detect_contradiction_uses_call_time_adapter(self):
        """Test that detect_contradiction() accepts call-time adapter."""
        call_time_adapter = Mock(spec=BaseAdapter)
        call_time_adapter.invoke.return_value = {
            "json_response": {"has_contradiction": False, "explanation": "...", "severity": "none"}
        }

        service = InferenceService()
        result = service.detect_contradiction(
            claim_a="A",
            claim_b="B",
            llm_adapter=call_time_adapter
        )

        assert call_time_adapter.invoke.called
        assert result["has_contradiction"] is False

    def test_detect_contradiction_raises_without_adapter(self):
        """Test that detect_contradiction() raises ValueError when no adapter."""
        service = InferenceService()

        with pytest.raises(ValueError, match="No LLM adapter provided"):
            service.detect_contradiction(claim_a="A", claim_b="B")

    def test_assess_source_quality_uses_call_time_adapter(self):
        """Test that assess_source_quality() accepts call-time adapter."""
        call_time_adapter = Mock(spec=BaseAdapter)
        call_time_adapter.invoke.return_value = {
            "json_response": {"reliability_score": 0.8, "bias_detected": False, "assessment": "..."}
        }

        service = InferenceService()
        result = service.assess_source_quality(
            url="https://example.com",
            content="content",
            llm_adapter=call_time_adapter
        )

        assert call_time_adapter.invoke.called
        assert result["reliability_score"] == 0.8

    def test_assess_source_quality_raises_without_adapter(self):
        """Test that assess_source_quality() raises ValueError when no adapter."""
        service = InferenceService()

        with pytest.raises(ValueError, match="No LLM adapter provided"):
            service.assess_source_quality(url="http://x.com", content="c")
