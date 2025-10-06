"""
This conftest.py file centralizes test fixtures for the entire application,
as outlined in ADR-TS-001. It provides a set of canonical, reusable fixtures
to eliminate redundant and inconsistent mocking logic across the test suite,
creating a modular and resilient testing architecture.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest


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
            "response_synthesizer_specialist": {
                "type": "llm",
                "llm_config": "default_llm",
                "prompt_file": "response_synthesizer_prompt.md"
            },
            # Add other specialist configs as needed for default tests
        },
        "specialist_model_bindings": {
            "router_specialist": "default_llm",
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
            # For EndSpecialist, we patch the internal `_execute_logic` methods of the classes
            # it depends on. This allows real instances to be created (passing isinstance checks)
            # while still mocking the execution logic for test isolation.
            with patch('app.src.specialists.response_synthesizer_specialist.ResponseSynthesizerSpecialist._execute_logic', return_value={}) as mock_synth_logic, \
                 patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._execute_logic', return_value={}) as mock_archive_logic:
                specialist_instance = SpecialistClass(
                    specialist_name=specialist_name,
                    specialist_config={
                        "response_synthesizer_specialist": mock_config_loader.get_config().get("specialists", {}).get("response_synthesizer_specialist", {}),
                        "archiver_specialist": mock_config_loader.get_config().get("specialists", {}).get("archiver_specialist", {}),
                    },
                    adapter_factory=mock_adapter_factory,
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
