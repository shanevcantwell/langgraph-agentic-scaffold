"""
Integration tests for InferenceService - Pure semantic judgment MCP service.

Tests validate the generic infer() method with live LLM calls.
Uses real ConfigLoader and AdapterFactory, not mocks.

ADR-CORE-020 Pattern: InferenceService uses the calling specialist's adapter,
not a dedicated binding. Tests use triage_architect's adapter as a stand-in.

MUST be run in Docker:
    docker compose exec app pytest app/tests/integration/test_inference_service_integration.py -v
"""

import pytest
from langchain_core.messages import HumanMessage

from app.src.mcp.services.inference_service import InferenceService, InferenceResponse
from app.src.mcp.registry import McpRegistry
from app.src.mcp.client import McpClient
from app.src.llm.factory import AdapterFactory
from app.src.utils.config_loader import ConfigLoader


@pytest.fixture
def config_loader():
    """Load real configuration."""
    return ConfigLoader()


@pytest.fixture
def adapter_factory(config_loader):
    """Create real adapter factory from config."""
    config = config_loader.get_config()
    return AdapterFactory(config)


@pytest.fixture
def llm_adapter(adapter_factory):
    """Get an LLM adapter for testing.

    ADR-CORE-020: InferenceService uses the calling specialist's adapter.
    For tests, we use triage_architect's adapter as a stand-in.
    """
    # Try triage_architect (commonly configured)
    adapter = adapter_factory.create_adapter("triage_architect", "")
    if adapter is not None:
        return adapter

    # Fallback to router
    adapter = adapter_factory.create_adapter("router", "")
    if adapter is not None:
        return adapter

    pytest.skip("No LLM adapter available (triage_architect or router must be configured)")


@pytest.fixture
def inference_service(llm_adapter):
    """Create InferenceService with adapter passed at init time.

    In real usage, specialists would pass their adapter at call time:
        result = inference_service.infer(..., llm_adapter=self.llm_adapter)

    For convenience in tests, we pass it at init time.
    """
    return InferenceService(llm_adapter=llm_adapter)


@pytest.fixture
def mcp_registry():
    """Create fresh MCP registry."""
    return McpRegistry({})


@pytest.fixture
def mcp_client_with_inference(mcp_registry, inference_service):
    """Create MCP client with InferenceService registered."""
    mcp_registry.register_service("inference_service", inference_service.get_mcp_functions())
    return McpClient(mcp_registry)


class TestInferenceServiceLive:
    """Integration tests for InferenceService with live LLM."""

    @pytest.mark.integration
    def test_infer_returns_structured_judgment(self, inference_service):
        """Test that infer() returns judgment, reasoning, and confidence from live LLM."""
        result = inference_service.infer(
            context="The Eiffel Tower is located in Paris, France. It was completed in 1889.",
            question="In which city is the Eiffel Tower located?"
        )

        # Should have all required fields
        assert "judgment" in result, f"Missing 'judgment' in result: {result}"
        assert "reasoning" in result, f"Missing 'reasoning' in result: {result}"
        assert "confidence" in result, f"Missing 'confidence' in result: {result}"

        # Judgment should mention Paris
        assert "paris" in result["judgment"].lower(), f"Expected 'Paris' in judgment: {result['judgment']}"

        # Confidence should be high for this clear-cut question
        assert result["confidence"] >= 0.7, f"Expected high confidence, got: {result['confidence']}"

    @pytest.mark.integration
    def test_infer_with_boolean_format(self, inference_service):
        """Test that boolean format hint produces yes/no judgment."""
        result = inference_service.infer(
            context="Water boils at 100 degrees Celsius at sea level.",
            question="Does water boil at 100 degrees Celsius at sea level?",
            output_format="boolean"
        )

        assert "judgment" in result
        # Should be yes/no or similar affirmative
        judgment_lower = result["judgment"].lower()
        assert any(word in judgment_lower for word in ["yes", "true", "correct", "affirmative"]), \
            f"Expected affirmative judgment for true statement, got: {result['judgment']}"

    @pytest.mark.integration
    def test_infer_with_category_format(self, inference_service):
        """Test that category format hint produces category-based judgment."""
        result = inference_service.infer(
            context="The company reported quarterly earnings of $2.5 billion, up 15% from last year.",
            question="Which category best describes this content: finance, legal, or HR?",
            output_format="category"
        )

        assert "judgment" in result
        # Should select finance
        judgment_lower = result["judgment"].lower()
        assert "finance" in judgment_lower, \
            f"Expected 'finance' category for earnings report, got: {result['judgment']}"

    @pytest.mark.integration
    def test_infer_handles_ambiguous_context(self, inference_service):
        """Test that infer() handles ambiguous/unclear context gracefully."""
        result = inference_service.infer(
            context="The thing happened at the place with the person.",
            question="What specific event occurred?"
        )

        assert "judgment" in result
        assert "reasoning" in result
        # Confidence should be lower for ambiguous context
        # (but we can't strictly assert this - LLM behavior varies)
        assert "confidence" in result


class TestInferenceServiceViaMcp:
    """Integration tests for InferenceService accessed via MCP client."""

    @pytest.mark.integration
    def test_infer_callable_via_mcp_client(self, mcp_client_with_inference):
        """Test that infer() is callable through MCP client."""
        result = mcp_client_with_inference.call(
            "inference_service",
            "infer",
            context="Python is a programming language.",
            question="What type of language is Python?"
        )

        assert "judgment" in result
        assert "programming" in result["judgment"].lower() or "language" in result["judgment"].lower()

    @pytest.mark.integration
    def test_mcp_service_exposes_all_functions(self, mcp_client_with_inference):
        """Test that all InferenceService methods are exposed via MCP."""
        services = mcp_client_with_inference.list_services()

        assert "inference_service" in services
        functions = services["inference_service"]

        # Verify all methods are registered
        assert "infer" in functions, "Generic infer() method not registered"
        assert "judge_relevance" in functions
        assert "detect_contradiction" in functions
        assert "assess_source_quality" in functions

    @pytest.mark.integration
    def test_judge_relevance_via_mcp(self, mcp_client_with_inference):
        """Test judge_relevance through MCP client."""
        result = mcp_client_with_inference.call(
            "inference_service",
            "judge_relevance",
            query="Python web frameworks",
            content="Django is a high-level Python web framework that encourages rapid development."
        )

        assert "is_relevant" in result
        assert result["is_relevant"] is True, f"Expected relevant content, got: {result}"


class TestCallTimeAdapterPattern:
    """Integration tests demonstrating ADR-CORE-020 call-time adapter pattern."""

    @pytest.mark.integration
    def test_infer_with_call_time_adapter(self, llm_adapter):
        """Test that infer() works when adapter is passed at call time.

        This is the primary usage pattern from ADR-CORE-020: specialists
        pass their own adapter to InferenceService methods.
        """
        service = InferenceService()  # No adapter at init

        result = service.infer(
            context="Machine learning is a subset of artificial intelligence.",
            question="What is machine learning a subset of?",
            llm_adapter=llm_adapter  # Adapter passed at call time
        )

        assert "judgment" in result
        assert "artificial intelligence" in result["judgment"].lower() or "ai" in result["judgment"].lower()

    @pytest.mark.integration
    def test_judge_relevance_with_call_time_adapter(self, llm_adapter):
        """Test judge_relevance with call-time adapter."""
        service = InferenceService()

        result = service.judge_relevance(
            query="database optimization",
            content="SQL indexes can significantly improve query performance.",
            llm_adapter=llm_adapter
        )

        assert "is_relevant" in result
        assert result["is_relevant"] is True


class TestInferenceServiceEdgeCases:
    """Integration tests for edge cases with live LLM."""

    @pytest.mark.integration
    def test_infer_with_very_long_context(self, inference_service):
        """Test that long context is handled (truncated) correctly."""
        # Create context longer than 4000 chars
        long_context = "This is important information. " * 200  # ~6000 chars

        result = inference_service.infer(
            context=long_context,
            question="What is the main topic of this text?"
        )

        # Should still return valid result despite truncation
        assert "judgment" in result
        assert "reasoning" in result

    @pytest.mark.integration
    def test_infer_with_technical_content(self, inference_service):
        """Test inference on technical/code content."""
        result = inference_service.infer(
            context="""
            def calculate_fibonacci(n):
                if n <= 1:
                    return n
                return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
            """,
            question="What algorithm does this code implement?"
        )

        assert "judgment" in result
        judgment_lower = result["judgment"].lower()
        assert "fibonacci" in judgment_lower, \
            f"Expected 'fibonacci' in judgment, got: {result['judgment']}"
