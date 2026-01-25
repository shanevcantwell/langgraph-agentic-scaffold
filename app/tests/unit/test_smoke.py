"""
Smoke tests - can the real system initialize?

These tests use REAL config, REAL ConfigLoader, REAL GraphBuilder.
No mocks for the initialization path. If these fail, nothing else matters.

Philosophy: 700 passing unit tests mean nothing if the app can't start.
These tests catch config/schema mismatches that mocked tests miss.
"""
import pytest


class TestSmoke:
    """Smoke tests for system initialization."""

    def test_config_loads(self):
        """Config loads without error using real ConfigLoader."""
        from app.src.utils.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.get_config()

        assert config is not None
        assert "specialists" in config
        assert "workflow" in config
        assert len(config["specialists"]) > 0

    def test_graph_builder_initializes(self):
        """GraphBuilder initializes with real config.

        This is THE critical smoke test. If GraphBuilder can't initialize
        with the real config.yaml, the API will crash on startup.

        This test would have caught the ADR-CORE-051 react: null bug.
        """
        from app.src.workflow.graph_builder import GraphBuilder

        # No mocks - use real ConfigLoader, real config.yaml
        builder = GraphBuilder()

        # Basic sanity checks
        assert builder.specialists is not None
        assert len(builder.specialists) > 0
        assert builder.config is not None

    def test_workflow_runner_initializes(self):
        """WorkflowRunner initializes (depends on GraphBuilder)."""
        from app.src.workflow.runner import WorkflowRunner

        # This creates GraphBuilder internally
        runner = WorkflowRunner()

        assert runner.builder is not None
        assert runner.specialists is not None
        assert len(runner.specialists) > 0

    def test_api_imports(self):
        """FastAPI app can be imported (triggers lifespan setup)."""
        # This import triggers the app creation, which can fail
        # if there are issues with the initialization path
        from app.src.api import app

        assert app is not None
