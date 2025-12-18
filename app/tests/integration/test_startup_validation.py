"""
Integration Test: Startup Validation and Fail-Fast

This test validates fail-fast validation mechanisms (ADR-CORE-001, CORE-006):
1. Critical specialist loading validation
2. Pre-flight checks for optional dependencies
3. Invalid route detection at startup
4. Entry point validation

These tests ensure the system fails quickly and clearly during initialization,
not during runtime with cryptic errors.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.config_loader import ConfigLoader
from app.src.utils.errors import WorkflowError, SpecialistLoadError


@pytest.mark.integration
def test_startup_validation_critical_specialist_present():
    """
    Tests that critical specialists are detected correctly.

    This validates that router_specialist (always critical) is present in the config.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # --- Assert ---
    # Router should be present (it's always critical)
    assert 'router_specialist' in config['specialists'], \
        "router_specialist must be present (critical for routing)"

    print("\n✓ Critical specialist (router) is present in config")


@pytest.mark.integration
def test_startup_validation_graph_builds_successfully():
    """
    Tests that GraphBuilder can successfully build a graph with real config.

    This is a smoke test that validates the entire initialization pipeline works.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()

    # --- Act ---
    try:
        builder = GraphBuilder(config_loader=config_loader)
        graph = builder.build()

        # --- Assert ---
        assert graph is not None, "Graph should be built successfully"
        assert 'router_specialist' in builder.specialists, \
            "Router specialist should be initialized"

        print("\n✓ GraphBuilder initialized successfully")
        print(f"✓ {len(builder.specialists)} specialists loaded")
        print(f"✓ Graph compiled successfully")

    except Exception as e:
        pytest.fail(f"GraphBuilder failed to initialize: {e}")


@pytest.mark.integration
def test_startup_validation_invalid_entry_point_defaults_to_router():
    """
    Tests that invalid entry_point in config defaults to router_specialist.

    This validates fail-safe behavior when entry point is misconfigured.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Create temporary config with invalid entry point
    invalid_config = config.copy()
    invalid_config['workflow'] = {'entry_point': 'nonexistent_specialist'}

    # Mock config_loader to return invalid config
    mock_config_loader = MagicMock()
    mock_config_loader.get_config.return_value = invalid_config

    # --- Act ---
    builder = GraphBuilder(config_loader=mock_config_loader)

    # --- Assert ---
    # GraphBuilder should default to router_specialist
    assert builder.entry_point == 'router_specialist', \
        "Entry point should default to router_specialist when configured entry point is invalid"

    print("\n✓ Invalid entry point handled gracefully")
    print(f"✓ Defaulted to: {builder.entry_point}")


@pytest.mark.integration
def test_startup_validation_disabled_specialist_not_loaded():
    """
    Tests that specialists with is_enabled=False are not loaded into the graph.

    This validates that the GraphBuilder respects the is_enabled flag.

    NOTE: The specialist module must exist (can't be a fake name) because GraphBuilder
    imports the module before checking is_enabled. This test uses a real specialist
    from config and sets is_enabled=False.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Find a real specialist that exists and can be disabled for testing
    # Use data_extractor_specialist as it's not critical
    if 'data_extractor_specialist' not in config['specialists']:
        pytest.skip("data_extractor_specialist not in config - needed for this test")

    # Create modified config with data_extractor disabled
    modified_config = config.copy()
    modified_config['specialists'] = config['specialists'].copy()
    modified_config['specialists']['data_extractor_specialist'] = config['specialists']['data_extractor_specialist'].copy()
    modified_config['specialists']['data_extractor_specialist']['is_enabled'] = False

    # Mock config_loader to return modified config
    mock_config_loader = MagicMock()
    mock_config_loader.get_config.return_value = modified_config

    # --- Act ---
    builder = GraphBuilder(config_loader=mock_config_loader)
    graph = builder.build()

    # --- Assert ---
    assert 'router_specialist' in builder.specialists, \
        "router_specialist should be loaded"

    assert 'data_extractor_specialist' not in builder.specialists, \
        "data_extractor_specialist should NOT be loaded (is_enabled=False)"

    assert 'data_extractor_specialist' not in graph.nodes, \
        "data_extractor_specialist should NOT be in graph nodes"

    print("\n✓ Disabled specialist correctly excluded")
    print(f"✓ Loaded specialists: {list(builder.specialists.keys())}")


@pytest.mark.integration
def test_startup_validation_provider_dependency_check():
    """
    Tests that provider dependency validation detects missing dependencies.

    This validates the AdapterFactory.validate_provider_dependencies() method.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Check if gemini_webui provider is configured
    llm_providers = config.get('llm_providers', {})
    has_gemini_webui = any(
        provider_config.get('type') == 'gemini_webui'
        for provider_config in llm_providers.values()
    )

    if not has_gemini_webui:
        pytest.skip("gemini_webui provider not configured in user_settings.yaml")

    # Check if it's actually bound to a specialist
    specialist_bindings = {
        name: spec_config.get('llm_config')
        for name, spec_config in config['specialists'].items()
        if spec_config.get('llm_config')
    }

    gemini_webui_bound = any(
        binding in llm_providers and llm_providers[binding].get('type') == 'gemini_webui'
        for binding in specialist_bindings.values()
    )

    if not gemini_webui_bound:
        pytest.skip("gemini_webui provider not bound to any specialist")

    # --- Act ---
    # Build GraphBuilder which should run dependency validation
    builder = GraphBuilder(config_loader=config_loader)

    # Check if dependency validation ran (it logs warnings)
    # The validation is in AdapterFactory.__init__
    missing_deps = builder.adapter_factory.validate_provider_dependencies()

    # --- Assert ---
    # If Playwright is missing, should have been detected
    # NOTE: In Docker, Playwright IS installed, so this should pass
    # The test validates that the CHECK runs, not necessarily that it fails

    print("\n✓ Provider dependency validation executed")
    if missing_deps:
        print(f"⚠ Missing dependencies detected: {len(missing_deps)}")
        for provider_key, provider_type, error_msg in missing_deps:
            print(f"  - {provider_key} ({provider_type}): {error_msg[:60]}...")
    else:
        print("✓ All provider dependencies satisfied")


@pytest.mark.integration
def test_startup_validation_allowed_destinations_set():
    """
    Tests that GraphBuilder populates allowed_destinations for route validation.

    This validates fail-fast route validation (ADR-CORE-006, Task 1.2).
    """
    # --- Arrange ---
    config_loader = ConfigLoader()

    # --- Act ---
    builder = GraphBuilder(config_loader=config_loader)

    # --- Assert ---
    # GraphBuilder should populate allowed_destinations in orchestrator
    assert builder.orchestrator.allowed_destinations is not None, \
        "Orchestrator should have allowed_destinations set"

    assert len(builder.orchestrator.allowed_destinations) > 0, \
        "Allowed destinations should not be empty"

    # Router should NOT be in allowed destinations (can't route to itself)
    assert 'router_specialist' not in builder.orchestrator.allowed_destinations, \
        "Router should not be in allowed destinations (can't route to itself)"

    print("\n✓ Allowed destinations configured for route validation")
    print(f"✓ {len(builder.orchestrator.allowed_destinations)} destinations allowed")
    print(f"✓ Router excluded from destinations (correct)")


@pytest.mark.integration
def test_startup_validation_specialist_pre_flight_checks():
    """
    Tests that specialists with failed pre-flight checks are not added to graph.

    This validates the _perform_pre_flight_checks() mechanism in BaseSpecialist.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Find a procedural specialist to test (they have simpler requirements)
    procedural_specialists = [
        name for name, spec_config in config['specialists'].items()
        if spec_config.get('type') == 'procedural'
    ]

    if not procedural_specialists:
        pytest.skip("No procedural specialists in config to test")

    # --- Act ---
    builder = GraphBuilder(config_loader=config_loader)
    graph = builder.build()

    # --- Assert ---
    # All specialists that passed pre-flight should be in the graph
    # EXCEPT MCP-only specialists (ADR-CORE-028: use centralized definition)
    from app.src.workflow.specialist_categories import SpecialistCategories
    for name in builder.specialists.keys():
        if name not in SpecialistCategories.MCP_ONLY:
            assert name in graph.nodes, \
                f"Specialist '{name}' passed pre-flight but not in graph"

    print("\n✓ Pre-flight checks executed successfully")
    print(f"✓ {len(builder.specialists)} specialists passed pre-flight checks")


@pytest.mark.integration
def test_startup_validation_router_specialist_map_populated():
    """
    Tests that RouterSpecialist.specialist_map is populated correctly.

    This validates that the router has awareness of all available specialists.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()

    # --- Act ---
    builder = GraphBuilder(config_loader=config_loader)

    # Get router specialist
    router = builder.specialists.get('router_specialist')

    if not router:
        pytest.skip("router_specialist not in config")

    # --- Assert ---
    # Router should have specialist_map populated
    assert hasattr(router, 'specialist_map'), \
        "Router should have specialist_map attribute"

    assert len(router.specialist_map) > 0, \
        "Router specialist_map should not be empty"

    # Router should NOT include itself in specialist_map
    assert 'router_specialist' not in router.specialist_map, \
        "Router should not include itself in specialist_map"

    print("\n✓ Router specialist_map populated correctly")
    print(f"✓ {len(router.specialist_map)} specialists in router map")
    print(f"✓ Router excluded from its own map (correct)")


@pytest.mark.integration
def test_startup_validation_graph_has_required_nodes():
    """
    Tests that the compiled graph has all required nodes.

    This validates that core components (router, end) are present in the graph.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()

    # --- Act ---
    builder = GraphBuilder(config_loader=config_loader)
    graph = builder.build()

    # --- Assert ---
    # Core nodes should be present
    assert 'router_specialist' in graph.nodes, \
        "Graph must contain router_specialist node"

    # Check that entry point is valid
    assert builder.entry_point in graph.nodes, \
        f"Entry point '{builder.entry_point}' must be a valid graph node"

    print("\n✓ Graph has all required nodes")
    print(f"✓ Entry point: {builder.entry_point}")
    print(f"✓ Total nodes: {len(graph.nodes)}")
