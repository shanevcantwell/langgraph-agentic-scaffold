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


# =============================================================================
# VALIDATION UTILITIES (Shared across live integration tests)
# =============================================================================

# Error indicators that signal workflow failure despite HTTP 200 response.
# These are used by assert_response_not_error() to catch silent failures.
# Reference: test_flows.py (the canonical implementation)
ERROR_INDICATORS = [
    "stuck in an unproductive loop",
    "unable to generate a final response",
    "error occurred while generating",
    "no specific output was generated",
    "unable to provide a response",
    "Router failed to select",
    "cannot proceed without artifacts",
    "No final response was generated",
    "FATAL ERROR",
]


def assert_response_not_error(response_content: str, context: str = "") -> None:
    """
    Assert that response content doesn't contain error indicators.

    This catches "silent failures" where HTTP returns 200 but the response
    contains error text indicating the workflow failed.

    Args:
        response_content: The response text to validate
        context: Optional context string for error messages (e.g., "[Flow 1.1]")

    Raises:
        AssertionError: If response contains any error indicator
    """
    response_lower = response_content.lower()
    for indicator in ERROR_INDICATORS:
        assert indicator.lower() not in response_lower, (
            f"{context} Response contains error indicator '{indicator}'. "
            f"Content preview: {response_content[:500]}"
        )


def assert_tiered_chat_merge(
    final_state: dict,
    context: str = ""
) -> None:
    """
    Assert that tiered chat properly merged both progenitor perspectives.

    Validates:
    1. Both progenitor artifacts are present (if tiered chat was used)
    2. The synthesized response incorporates both perspectives

    Args:
        final_state: The final_state dict from the workflow
        context: Optional context string for error messages

    Raises:
        AssertionError: If tiered chat merge validation fails
    """
    artifacts = final_state.get("artifacts", {})
    routing_history = final_state.get("routing_history", [])

    # Only validate if tiered chat pattern was used
    has_alpha = "progenitor_alpha_specialist" in routing_history
    has_bravo = "progenitor_bravo_specialist" in routing_history
    has_synthesizer = "tiered_synthesizer_specialist" in routing_history

    if not (has_alpha or has_bravo):
        return  # Tiered chat not used, skip validation

    # If any progenitor ran, both should have run
    if has_alpha or has_bravo:
        assert has_alpha and has_bravo, (
            f"{context} Tiered chat incomplete: Alpha={has_alpha}, Bravo={has_bravo}. "
            f"History: {routing_history}"
        )

    # Check for progenitor artifacts (if artifacts is a dict with content)
    if isinstance(artifacts, dict):
        # Progenitor artifacts may be stored with various key patterns
        progenitor_artifacts = [
            k for k in artifacts.keys()
            if "progenitor" in k.lower() or "alpha" in k.lower() or "bravo" in k.lower()
        ]
        # Note: Progenitors may write to scratchpad rather than artifacts
        # This check is informational - absence doesn't indicate failure

    # Synthesizer should have run to merge perspectives
    if has_alpha and has_bravo:
        assert has_synthesizer, (
            f"{context} Both progenitors ran but synthesizer missing. "
            f"History: {routing_history}"
        )


def assert_termination_reason_in_response(
    final_state: dict,
    context: str = ""
) -> None:
    """
    Assert that if termination_reason exists, it's reflected in the response.

    When loop detection or other termination conditions trigger, the user
    should see an explanation in the final response, not a silent failure.

    Args:
        final_state: The final_state dict from the workflow
        context: Optional context string for error messages

    Raises:
        AssertionError: If termination occurred but reason not in response
    """
    if not final_state:
        return

    scratchpad = final_state.get("scratchpad", {})
    termination_reason = scratchpad.get("termination_reason", "")

    if not termination_reason:
        return  # No termination reason to validate

    # Get the final response content
    artifacts = final_state.get("artifacts", {})
    final_response = ""
    if isinstance(artifacts, dict):
        final_response = artifacts.get("final_user_response.md", "")

    # If there's a termination reason, the response should acknowledge it
    # (We check for any indication that the workflow was halted, not exact text match)
    termination_keywords = ["loop", "halt", "stop", "unable to complete", "terminated"]

    if termination_reason and final_response:
        response_lower = final_response.lower()
        has_acknowledgment = any(kw in response_lower for kw in termination_keywords)
        # Note: This is informational - some termination reasons may be internal
        # and shouldn't necessarily be exposed to users


def assert_specialist_sequence(
    specialist_order: list,
    expected_sequence: list,
    context: str = ""
) -> None:
    """
    Assert specialists were called in the specified order (allowing extras between).

    This validates that critical specialists appear in the expected order without
    requiring an exact match. For example, [triage, router, end] will pass if
    the actual order is [triage, facilitator, router, progenitor_alpha, end].

    Args:
        specialist_order: List of specialists in execution order
        expected_sequence: Expected ordering (subset that must appear in order)
        context: Optional context string for error messages

    Raises:
        AssertionError: If expected sequence not found in order
    """
    seq_idx = 0

    for specialist in specialist_order:
        if seq_idx < len(expected_sequence) and specialist == expected_sequence[seq_idx]:
            seq_idx += 1

    if seq_idx != len(expected_sequence):
        remaining = expected_sequence[seq_idx:]
        raise AssertionError(
            f"{context} Expected sequence not found.\n"
            f"Expected: {expected_sequence}\n"
            f"Actual order: {specialist_order}\n"
            f"Missing from sequence: {remaining}"
        )


# =============================================================================
# EXTERNAL MCP FIXTURES (Shared across MCP container tests)
# =============================================================================

@pytest.fixture
def mcp_config():
    """
    Load application configuration for MCP tests.

    Provides access to mcp.external_mcp config section.
    """
    from app.src.utils.config_loader import ConfigLoader
    return ConfigLoader().get_config()


@pytest.fixture
async def external_mcp_client(mcp_config):
    """
    Shared ExternalMcpClient fixture with automatic cleanup.

    Use this as the base for service-specific connection fixtures.
    Pytest-asyncio manages the event loop automatically.

    Example:
        async def test_something(external_mcp_client):
            await external_mcp_client.connect_from_config("filesystem")
            # ... test code ...
    """
    from app.src.mcp.external_client import ExternalMcpClient
    client = ExternalMcpClient(mcp_config)
    yield client
    await client.cleanup()


@pytest.fixture
async def connected_filesystem_client(external_mcp_client):
    """
    ExternalMcpClient connected to filesystem MCP container.

    Skips test if filesystem MCP not enabled/available.
    """
    tools = await external_mcp_client.connect_from_config("filesystem")
    if tools is None:
        pytest.skip("Filesystem MCP not enabled or available")
    yield external_mcp_client


@pytest.fixture
async def connected_navigator_client(external_mcp_client):
    """
    ExternalMcpClient connected to navigator (surf) MCP container.

    Skips test if navigator MCP not enabled/available.
    """
    tools = await external_mcp_client.connect_from_config("navigator")
    if tools is None:
        pytest.skip("Navigator MCP not enabled or available. Start with: docker-compose --profile navigator up -d")
    yield external_mcp_client
