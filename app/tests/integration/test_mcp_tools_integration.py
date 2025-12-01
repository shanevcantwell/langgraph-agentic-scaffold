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
def file_specialist_with_registry(mcp_registry, tmp_path):
    """
    Create FileSpecialist with MCP registration using tmp_path as root.

    This allows testing file operations in an isolated temporary directory.
    """
    from app.src.specialists.file_specialist import FileSpecialist

    # Create specialist with tmp_path as root directory
    specialist = FileSpecialist(
        specialist_name="file_specialist",
        specialist_config={"root_dir": str(tmp_path)}
    )

    # Register MCP services
    specialist.register_mcp_services(mcp_registry)

    return specialist, tmp_path


@pytest.fixture
def web_specialist_with_registry(mcp_registry):
    """Create WebSpecialist with MCP registration."""
    from app.src.specialists.web_specialist import WebSpecialist
    from app.src.strategies.search.duckduckgo_strategy import DuckDuckGoSearchStrategy

    specialist = WebSpecialist(
        specialist_name="web_specialist",
        specialist_config={},
        search_strategy=DuckDuckGoSearchStrategy()
    )

    # Register MCP services
    specialist.register_mcp_services(mcp_registry)

    return specialist


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
# FILE SPECIALIST MCP TESTS
# =============================================================================

class TestFileSpecialistMcp:
    """Test all file_specialist MCP functions."""

    def test_file_exists_returns_false_for_missing_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify file_exists returns False for non-existent file."""
        _, tmp_path = file_specialist_with_registry

        result = mcp_client.call(
            "file_specialist",
            "file_exists",
            path="nonexistent.txt"
        )

        assert result is False

    def test_file_exists_returns_true_for_existing_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify file_exists returns True for existing file."""
        _, tmp_path = file_specialist_with_registry

        # Create a test file
        test_file = tmp_path / "exists.txt"
        test_file.write_text("test content")

        result = mcp_client.call(
            "file_specialist",
            "file_exists",
            path="exists.txt"
        )

        assert result is True

    def test_write_and_read_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify write_file and read_file work together."""
        _, tmp_path = file_specialist_with_registry

        test_content = "Hello, MCP testing!"

        # Write file - returns success message string
        write_result = mcp_client.call(
            "file_specialist",
            "write_file",
            path="test_write.txt",
            content=test_content
        )

        assert write_result  # Truthy (success message string)
        assert "Successfully" in write_result or "wrote" in write_result.lower()

        # Read file back
        read_result = mcp_client.call(
            "file_specialist",
            "read_file",
            path="test_write.txt"
        )

        assert read_result == test_content

    def test_append_to_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify append_to_file adds content to existing file."""
        _, tmp_path = file_specialist_with_registry

        # Create initial file
        mcp_client.call(
            "file_specialist",
            "write_file",
            path="append_test.txt",
            content="Line 1\n"
        )

        # Append to file
        mcp_client.call(
            "file_specialist",
            "append_to_file",
            path="append_test.txt",
            content="Line 2\n"
        )

        # Read back
        content = mcp_client.call(
            "file_specialist",
            "read_file",
            path="append_test.txt"
        )

        assert "Line 1" in content
        assert "Line 2" in content

    def test_list_files(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify list_files returns directory contents."""
        _, tmp_path = file_specialist_with_registry

        # Create some test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        result = mcp_client.call(
            "file_specialist",
            "list_files",
            path="."
        )

        assert isinstance(result, list)
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir" in result

    def test_create_directory(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify create_directory creates new directory."""
        _, tmp_path = file_specialist_with_registry

        result = mcp_client.call(
            "file_specialist",
            "create_directory",
            path="new_directory"
        )

        assert result  # Truthy (success message string)
        assert (tmp_path / "new_directory").is_dir()

    def test_rename_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify rename_file moves/renames files."""
        _, tmp_path = file_specialist_with_registry

        # Create original file
        (tmp_path / "original.txt").write_text("content")

        result = mcp_client.call(
            "file_specialist",
            "rename_file",
            old_path="original.txt",
            new_path="renamed.txt"
        )

        assert result  # Truthy (success message string)
        assert not (tmp_path / "original.txt").exists()
        assert (tmp_path / "renamed.txt").exists()

    def test_delete_file(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify delete_file removes files."""
        _, tmp_path = file_specialist_with_registry

        # Create file to delete
        test_file = tmp_path / "to_delete.txt"
        test_file.write_text("delete me")

        result = mcp_client.call(
            "file_specialist",
            "delete_file",
            path="to_delete.txt"
        )

        assert result  # Truthy (success message string)
        assert not test_file.exists()

    def test_create_zip(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify create_zip creates archive from directory."""
        _, tmp_path = file_specialist_with_registry

        # Create source directory with files
        source_dir = tmp_path / "to_zip"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        # Note: Parameter is destination_path, not output_path
        result = mcp_client.call(
            "file_specialist",
            "create_zip",
            source_path="to_zip",
            destination_path="archive.zip"
        )

        assert result  # Truthy (success message string)
        assert (tmp_path / "archive.zip").exists()

    def test_create_manifest(
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify create_manifest creates valid JSON manifest."""
        _, tmp_path = file_specialist_with_registry

        # AtomicManifest schema requires run_id and final_response_generated
        manifest_data = {
            "run_id": "test-run-12345",
            "final_response_generated": True,
            "routing_history": ["router", "chat_specialist", "end_specialist"],
            "artifacts": [],
            "termination_reason": "success"
        }

        result = mcp_client.call(
            "file_specialist",
            "create_manifest",
            path="manifest.json",
            data=manifest_data
        )

        assert result  # Truthy (success message string)
        assert (tmp_path / "manifest.json").exists()

        # Verify JSON content
        content = (tmp_path / "manifest.json").read_text()
        parsed = json.loads(content)
        assert parsed["run_id"] == "test-run-12345"
        assert parsed["final_response_generated"] is True


# =============================================================================
# WEB SPECIALIST MCP TESTS
# =============================================================================

class TestWebSpecialistMcp:
    """Test web_specialist MCP functions."""

    def test_search_function_registered(
        self, mcp_client, web_specialist_with_registry
    ):
        """Verify search function is registered in MCP."""
        services = mcp_client.list_services()

        assert "web_specialist" in services
        assert "search" in services["web_specialist"]

    def test_search_returns_results(
        self, mcp_client, web_specialist_with_registry
    ):
        """Verify search function returns list of results."""
        # Note: web_specialist.search() uses DuckDuckGo strategy
        # This test verifies the MCP plumbing works
        result = mcp_client.call(
            "web_specialist",
            "search",
            query="test query",
            max_results=5
        )

        assert isinstance(result, list)


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
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify calling non-existent function raises appropriate error."""
        with pytest.raises(ValueError) as exc_info:
            mcp_client.call(
                "file_specialist",
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
        self, mcp_client, file_specialist_with_registry
    ):
        """Verify list_services returns all registered services."""
        services = mcp_client.list_services()

        assert isinstance(services, dict)
        assert "file_specialist" in services
        assert len(services["file_specialist"]) == 10  # 10 file functions

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
        expected_services = [
            "file_specialist",
            # "researcher_specialist", # Removed in Phase 1
            "summarizer_specialist",
            "image_specialist",
        ]

        for service in expected_services:
            assert service in services, (
                f"Expected MCP service '{service}' not registered. "
                f"Available: {list(services.keys())}"
            )

    def test_file_specialist_accessible_from_graph(self, full_graph_mcp_client):
        """Verify file_specialist MCP functions work from graph context."""
        services = full_graph_mcp_client.list_services()

        # file_specialist should have all 10 functions
        if "file_specialist" in services:
            file_funcs = services["file_specialist"]
            expected_funcs = [
                "file_exists", "read_file", "write_file", "append_to_file",
                "delete_file", "list_files", "create_directory", "rename_file",
                "create_zip", "create_manifest"
            ]
            for func in expected_funcs:
                assert func in file_funcs, (
                    f"Expected function '{func}' in file_specialist. "
                    f"Available: {file_funcs}"
                )
