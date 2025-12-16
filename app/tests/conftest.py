"""
This conftest.py file centralizes test fixtures for the entire application,
as outlined in ADR-TS-001. It provides a set of canonical, reusable fixtures
to eliminate redundant and inconsistent mocking logic across the test suite,
creating a modular and resilient testing architecture.
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

def is_docker() -> bool:
    """Detect if running inside Docker container."""
    return os.path.exists("/.dockerenv") or bool(os.environ.get("DOCKER_CONTAINER"))


def pytest_configure(config):
    """Print environment banner at test session start."""
    if not is_docker():
        print("\n" + "=" * 70)
        print("  RUNNING OUTSIDE DOCKER")
        print("  Tests in integration/ folder will be skipped automatically")
        print("  Reason: .env is configured for Docker proxy to reach LMStudio/3090")
        print("  For full test suite: docker compose exec app pytest")
        print("=" * 70 + "\n")


@pytest.fixture(autouse=True)
def skip_integration_outside_docker(request):
    """
    For tests requiring Docker environment:
    - Skip with informative message explaining the limitation
    - This is NOT silent - pytest shows the skip reason prominently

    Triggers on:
    - Markers: integration, live_llm, archive
    - Location: tests/integration/ folder (regardless of markers)
    """
    if is_docker():
        return  # All tests run inside Docker

    # Check markers
    markers = {m.name for m in request.node.iter_markers()}
    docker_required_markers = {"integration", "live_llm", "archive"}

    # Check if test is in integration folder
    test_path = str(request.fspath)
    in_integration_folder = "/integration/" in test_path

    if (markers & docker_required_markers) or in_integration_folder:
        pytest.skip(
            "This test requires Docker. "
            "Reason: .env is configured for Docker proxy and Docker paths (/app/logs/). "
            "Fix: Run 'docker compose exec app pytest' instead."
        )


# =============================================================================
# TEST FIXTURES (ADR-TS-001)
# =============================================================================

@pytest.fixture
def mock_config_loader() -> MagicMock:
    """
    (ADR-TS-001, Task 1.1) Creates a mock of the ConfigLoader.

    This fixture returns a MagicMock of the ConfigLoader, pre-configured
    with a default, valid configuration dictionary. Tests can override this
    default config by modifying the return_value of the mock's get_config method.

    Example in a test:
        mock_config_loader.get_config.return_value['specialists']['router_specialist']['model'] = 'new_model'
    """
    mock = MagicMock()
    default_config = {
        "llm_providers": {
            "default_llm": {
                "type": "gemini",
                "api_identifier": "gemini-1.5-flash",
            }
        },
        "specialists": {
            "router_specialist": {
                "type": "llm",
                "model": "default_llm",
                "prompt_template": "router_specialist.md",
            },
            "end_specialist": {
                "type": "hybrid",
                "llm_config": "default_llm",
                "synthesis_prompt_file": "response_synthesizer_prompt.md",
                "archiver_config": {
                    "type": "procedural",
                    "archive_path": "./logs/archive",
                    "pruning_strategy": "count",
                    "pruning_max_count": 50
                }
            },
            # Add other specialist configs as needed for default tests
        },
        "specialist_model_bindings": {
            "router_specialist": "default_llm",
            "end_specialist": "default_llm",
        },
    }
    mock.get_config.return_value = default_config
    return mock


@pytest.fixture
def mock_adapter_factory() -> MagicMock:
    """
    (ADR-TS-001, Task 1.2) Creates a mock of the AdapterFactory.

    This fixture returns a MagicMock of the AdapterFactory. Its `create_adapter`
    method is configured to return another MagicMock by default, representing
    a generic, mocked LLM adapter.
    """
    mock = MagicMock()
    mock.create_adapter.return_value = MagicMock(name="mock_llm_adapter")
    return mock


@pytest.fixture
def initialized_specialist_factory(
    mock_config_loader: MagicMock, mock_adapter_factory: MagicMock
):
    """
    (ADR-TS-001, Task 1.3) A factory fixture to create initialized specialists.

    This is a factory function that encapsulates the complex instantiation logic
    for any specialist. It takes a specialist's class name and returns a fully
    initialized instance with its core dependencies (ConfigLoader, AdapterFactory,
    llm_adapter) correctly mocked.

    This fixture is the cornerstone of the new testing strategy, making it trivial
    for any test to get a valid subject under test (SUT).

    Usage in a test:
        router = initialized_specialist_factory("RouterSpecialist")
    """

    def _factory(
        class_name: str,
        specialist_name_override: str = None,
        config_override: dict = None,
    ):
        """
        Dynamically imports and instantiates a specialist class, then binds
        its mocked dependencies.

        Args:
            class_name: The string name of the specialist class (e.g., "RouterSpecialist").
            specialist_name_override: Optional name to use for config lookups, if different
                                      from the auto-derived name.

        Returns:
            An initialized instance of the specialist with mocked dependencies.
        """
        # Dynamically find and import the specialist module
        module_name_snake = "".join(
            ["_" + i.lower() if i.isupper() else i for i in class_name]
        ).lstrip("_")
        module = importlib.import_module(f"app.src.specialists.{module_name_snake}")
        SpecialistClass = getattr(module, class_name)

        # Determine the specialist's name for config lookup
        specialist_name = specialist_name_override or "".join(
            ["_" + i.lower() if i.isupper() else i for i in class_name]
        ).lstrip("_")

        # Get the base config and apply any overrides
        specialist_config = (
            mock_config_loader.get_config()
            .get("specialists", {})
            .get(specialist_name, {})
        )
        if config_override:
            specialist_config.update(config_override)

        # Step 1: Instantiate the specialist, handling special cases
        if class_name == "EndSpecialist":
            # For EndSpecialist, we patch the archiver's `_execute_logic` method.
            # EndSpecialist no longer depends on ResponseSynthesizerSpecialist as a separate class.
            # It performs synthesis inline using its own LLM adapter.
            with patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._execute_logic', return_value={}) as mock_archive_logic:
                specialist_instance = SpecialistClass(
                    specialist_name=specialist_name,
                    specialist_config=specialist_config
                )
        elif class_name == "CriticSpecialist":
            # CriticSpecialist requires a strategy object at initialization.
            # We'll create a mock strategy to satisfy the constructor,
            # allowing tests to mock its methods as needed.
            from app.src.strategies.critique.base import BaseCritiqueStrategy
            mock_strategy = MagicMock(spec=BaseCritiqueStrategy)
            
            specialist_instance = SpecialistClass(
                specialist_name=specialist_name,
                specialist_config=specialist_config,
                critique_strategy=mock_strategy,
            )
            # The strategy itself might need an adapter, so we'll attach one.
            mock_strategy.llm_adapter = mock_adapter_factory.create_adapter(specialist_name)

        else:
            # Standard instantiation for most specialists
            specialist_instance = SpecialistClass(
                specialist_name=specialist_name,
                specialist_config=specialist_config,
            )

        # Step 2: Simulate GraphBuilder's logic by creating and binding the mock adapter
        mock_llm_adapter = mock_adapter_factory.create_adapter(specialist_name)
        specialist_instance.llm_adapter = mock_llm_adapter

        return specialist_instance

    return _factory
