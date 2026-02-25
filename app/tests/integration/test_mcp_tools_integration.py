# app/tests/integration/test_mcp_tools_integration.py
"""
Comprehensive integration tests for MCP (Message-Centric Protocol) tools.

Tests that all registered MCP services and their functions work correctly.
Uses real MCP registry with actual specialist implementations.

MCP Services Tested:
- file_specialist: 10 file system operations
- researcher_specialist: search function
- summarizer_specialist: summarize function
- image_specialist: describe function
"""
import pytest
import os
import json
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.src.mcp.registry import McpRegistry
from app.src.mcp.client import McpClient
from app.src.mcp.schemas import McpRequest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mcp_config():
    """Minimal MCP configuration for testing."""
    return {
        "mcp": {
            "tracing_enabled": False,  # Disable tracing for faster tests
            "timeout_seconds": 10,  # Generous timeout for tests
        }
    }


@pytest.fixture
def mcp_registry(mcp_config):
    """Create a fresh MCP registry for testing."""
    return McpRegistry(mcp_config)


@pytest.fixture
def mcp_client(mcp_registry):
    """Create MCP client wrapper."""
    return McpClient(mcp_registry)


@pytest.fixture
def summarizer_specialist_with_registry(mcp_registry):
    """Create SummarizerSpecialist with MCP registration and mocked LLM."""
    from app.src.specialists.summarizer_specialist import SummarizerSpecialist

    specialist = SummarizerSpecialist(
        specialist_name="summarizer_specialist",
        specialist_config={}
    )

    # Mock the LLM adapter for summarization
    mock_adapter = MagicMock()
    mock_adapter.invoke.return_value = {
        "text_response": "This is a summarized version of the input text."
    }
    specialist.llm_adapter = mock_adapter

    # Register MCP services
    specialist.register_mcp_services(mcp_registry)

    return specialist


@pytest.fixture
def image_specialist_with_registry(mcp_registry):
    """Create ImageSpecialist with MCP registration and mocked LLM."""
    from app.src.specialists.image_specialist import ImageSpecialist

    specialist = ImageSpecialist(
        specialist_name="image_specialist",
        specialist_config={}
    )

    # Mock the LLM adapter for image description
    mock_adapter = MagicMock()
    mock_adapter.invoke.return_value = {
        "text_response": "This image shows a landscape with mountains and trees."
    }
    specialist.llm_adapter = mock_adapter

    # Register MCP services
    specialist.register_mcp_services(mcp_registry)

    return specialist


# =============================================================================
# NOTE: TestFileSpecialistMcp removed - file_specialist superseded by external
# filesystem MCP container (ADR-CORE-035). Coverage now in test_filesystem_mcp.py
# =============================================================================


# =============================================================================
# SUMMARIZER SPECIALIST MCP TESTS
# =============================================================================

class TestSummarizerSpecialistMcp:
    """Test summarizer_specialist MCP functions."""

    def test_summarize_function_registered(
        self, mcp_client, summarizer_specialist_with_registry
    ):
        """Verify summarize function is registered in MCP."""
        services = mcp_client.list_services()

        assert "summarizer_specialist" in services
        assert "summarize" in services["summarizer_specialist"]

    def test_summarize_returns_text(
        self, mcp_client, summarizer_specialist_with_registry
    ):
        """Verify summarize function returns summarized text."""
        long_text = """
        This is a long piece of text that needs to be summarized.
        It contains multiple sentences and paragraphs.
        The summary should be shorter than the original.
        """ * 10

        result = mcp_client.call(
            "summarizer_specialist",
            "summarize",
            text=long_text,
            max_length=100
        )

        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# IMAGE SPECIALIST MCP TESTS
# =============================================================================

class TestImageSpecialistMcp:
    """Test image_specialist MCP functions."""

    def test_describe_function_registered(
        self, mcp_client, image_specialist_with_registry
    ):
        """Verify describe function is registered in MCP."""
        services = mcp_client.list_services()

        assert "image_specialist" in services
        assert "describe" in services["image_specialist"]

    def test_describe_returns_description(
        self, mcp_client, image_specialist_with_registry
    ):
        """Verify describe function returns image description."""
        # Create a minimal base64-encoded image (1x1 pixel PNG)
        # This is a valid PNG but minimal for testing
        test_image_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )

        result = mcp_client.call(
            "image_specialist",
            "describe",
            base64_image=test_image_b64,
            prompt="What is in this image?"
        )

        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# MCP ERROR HANDLING TESTS
# =============================================================================

class TestMcpErrorHandling:
    """Test MCP error handling and edge cases."""

    def test_call_nonexistent_service_raises_error(self, mcp_client, mcp_registry):
        """Verify calling non-existent service raises appropriate error."""
        with pytest.raises(ValueError) as exc_info:
            mcp_client.call(
                "nonexistent_service",
                "some_function"
            )

        assert "not found" in str(exc_info.value).lower()

    def test_call_nonexistent_function_raises_error(
        self, mcp_client, summarizer_specialist_with_registry
    ):
        """Verify calling non-existent function raises appropriate error."""
        with pytest.raises(ValueError) as exc_info:
            mcp_client.call(
                "summarizer_specialist",
                "nonexistent_function"
            )

        assert "not found" in str(exc_info.value).lower()

    def test_call_safe_returns_false_on_error(self, mcp_client, mcp_registry):
        """Verify call_safe returns (False, error_msg) on failure."""
        success, result = mcp_client.call_safe(
            "nonexistent_service",
            "some_function"
        )

        assert success is False
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# MCP REGISTRY TESTS
# =============================================================================

class TestMcpRegistry:
    """Test MCP registry functionality."""

    def test_list_services_returns_all_registered(
        self, mcp_client, summarizer_specialist_with_registry
    ):
        """Verify list_services returns all registered services."""
        services = mcp_client.list_services()

        assert isinstance(services, dict)
        assert "summarizer_specialist" in services
        assert "summarize" in services["summarizer_specialist"]

    def test_registry_isolation(self, mcp_config):
        """Verify each registry instance is isolated."""
        registry1 = McpRegistry(mcp_config)
        registry2 = McpRegistry(mcp_config)

        # Register service in registry1 only
        registry1.register_service("test_service", {
            "test_func": lambda: "test"
        })

        # registry2 should not have the service
        assert "test_service" in registry1.list_services()
        assert "test_service" not in registry2.list_services()


# =============================================================================
# MCP INTEGRATION WITH GRAPH TESTS
# =============================================================================

class TestMcpGraphIntegration:
    """Test MCP integration with full graph context."""

    @pytest.fixture
    def full_graph_mcp_client(self):
        """
        Create MCP client with full graph initialization.

        This tests MCP in the context of a real graph with all specialists.
        """
        from app.src.workflow.graph_builder import GraphBuilder
        from app.src.utils.config_loader import ConfigLoader

        config_loader = ConfigLoader()
        builder = GraphBuilder(config_loader=config_loader)

        # The registry is populated during graph building
        return McpClient(builder.mcp_registry)

    def test_all_mcp_services_registered_in_graph(self, full_graph_mcp_client):
        """Verify all expected MCP services are registered in full graph."""
        services = full_graph_mcp_client.list_services()

        # These services should be registered
        # NOTE: file_specialist removed per ADR-CORE-035 (external filesystem MCP)
        expected_services = [
            # "file_specialist",  # Removed - superseded by external filesystem MCP (ADR-CORE-035)
            # "researcher_specialist", # Removed in Phase 1
            "summarizer_specialist",
            "image_specialist",
        ]

        for service in expected_services:
            assert service in services, (
                f"Expected MCP service '{service}' not registered. "
                f"Available: {list(services.keys())}"
            )

    def test_image_specialist_accessible_from_graph(self, full_graph_mcp_client):
        """Verify image_specialist MCP functions work from graph context."""
        services = full_graph_mcp_client.list_services()

        # image_specialist should have describe function
        assert "image_specialist" in services, (
            f"image_specialist not found. Available: {list(services.keys())}"
        )
        image_funcs = services["image_specialist"]
        assert "describe" in image_funcs, (
            f"Expected function 'describe' in image_specialist. "
            f"Available: {image_funcs}"
        )
