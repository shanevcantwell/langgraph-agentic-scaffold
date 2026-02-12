"""
Integration Test: Config Validation Smoke Test

This test validates that the real config.yaml file can be successfully loaded
by GraphBuilder without errors. It catches issues like:
- Missing required specialist configuration fields
- Invalid specialist type definitions
- Malformed YAML structure
- Missing LLM provider configurations

This is a SMOKE TEST that prevents deployment of broken config files.
"""
import pytest
from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.config_loader import ConfigLoader
from app.src.utils.errors import SpecialistLoadError, WorkflowError


@pytest.mark.integration
def test_real_config_loads_successfully():
    """
    Validates that the actual config.yaml can be loaded by GraphBuilder.

    This smoke test catches configuration errors that unit tests miss because
    they use mocked config fixtures. Real config errors (like missing
    critique_strategy for CriticSpecialist) should be caught here before
    reaching production.

    This test will FAIL if:
    - config.yaml has syntax errors
    - Required specialist fields are missing (e.g., critique_strategy)
    - LLM provider bindings are invalid
    - GraphBuilder cannot compile the graph
    """
    # Load real config (no mocking)
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Verify config is not empty
    assert config is not None, "ConfigLoader returned None"
    assert 'specialists' in config, "config.yaml missing 'specialists' section"
    assert 'workflow' in config, "config.yaml missing 'workflow' section"

    # Attempt to build graph with real config
    # This will fail if any specialist config is malformed
    try:
        builder = GraphBuilder(config_loader=config_loader)
        graph = builder.build()

        # Verify graph was built successfully
        assert graph is not None, "GraphBuilder.build() returned None"

        # Verify expected critical specialists are present
        assert 'router_specialist' in builder.specialists, \
            "router_specialist not loaded (required for routing)"

        print(f"\n✓ Real config.yaml loaded successfully")
        print(f"✓ {len(builder.specialists)} specialists initialized")
        print(f"✓ Graph compiled without errors")

    except SpecialistLoadError as e:
        pytest.fail(
            f"SpecialistLoadError during config loading: {e}\n"
            f"This indicates a specialist configuration is malformed in config.yaml"
        )
    except WorkflowError as e:
        pytest.fail(
            f"WorkflowError during graph building: {e}\n"
            f"This indicates a workflow configuration issue in config.yaml"
        )
    except Exception as e:
        pytest.fail(
            f"Unexpected error loading config: {e}\n"
            f"Check config.yaml for syntax errors or missing required fields"
        )




@pytest.mark.integration
def test_all_llm_specialists_have_valid_model_bindings():
    """
    Validates that all LLM specialists have valid model bindings.

    Checks that:
    1. user_settings.yaml defines llm_providers
    2. All LLM/hybrid specialists get an llm_config binding
    3. All bindings reference valid providers

    Note: default_llm_config is processed during config merge but not retained
    in the final merged config. It's used to assign bindings to specialists,
    so we verify that LLM specialists HAVE bindings, not that default exists.
    """
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Get LLM provider definitions
    llm_providers = config.get('llm_providers', {})
    assert len(llm_providers) > 0, \
        "user_settings.yaml must define at least one llm_provider"

    # Check that all LLM/hybrid specialists have valid llm_config bindings
    specialists = config.get('specialists', {})
    unbound_llm_specialists = []
    invalid_bindings = []

    for name, spec_config in specialists.items():
        spec_type = spec_config.get('type')

        # Only LLM and hybrid specialists need bindings
        if spec_type in ['llm', 'hybrid']:
            llm_config = spec_config.get('llm_config')

            if not llm_config:
                unbound_llm_specialists.append(name)
            elif llm_config not in llm_providers:
                invalid_bindings.append((name, llm_config))

    # Assert no LLM specialists are missing bindings
    assert len(unbound_llm_specialists) == 0, \
        f"LLM specialists without model bindings: {unbound_llm_specialists}\n" \
        f"Add bindings in user_settings.yaml or set default_llm_config"

    # Assert all bindings reference valid providers
    assert len(invalid_bindings) == 0, \
        f"Specialists with invalid provider references: {invalid_bindings}\n" \
        f"Available providers: {list(llm_providers.keys())}"

    print(f"\n✓ {len(llm_providers)} LLM providers defined")
    print(f"✓ All LLM/hybrid specialists have valid bindings")
    print(f"✓ Total specialists: {len(specialists)}")
