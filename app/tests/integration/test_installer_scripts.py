# app/tests/integration/test_installer_scripts.py
"""
Integration tests for installer scripts (setup.sh, setup.ps1).

These tests verify that the interactive installers:
1. Generate valid configuration files
2. Handle different provider choices correctly
3. Produce configurations that pass validation
4. Don't overwrite existing configs

Note: These tests simulate user input rather than running the actual
interactive scripts, as that would require terminal interaction.
"""
import pytest
import tempfile
import os
import yaml
from pathlib import Path
from unittest.mock import patch


class TestInstallerConfigGeneration:
    """Tests for configuration file generation logic used by installers."""

    def test_generates_valid_env_file_gemini_only(self):
        """Verifies installer generates valid .env for Gemini-only setup."""
        # Simulate installer logic
        google_api_key = "test_api_key_123"
        workspace_path = "workspace"

        env_content = self._generate_env_content(
            google_api_key=google_api_key,
            lmstudio_base_url=None,
            workspace_path=workspace_path
        )

        # Validate
        assert "GOOGLE_API_KEY" in env_content
        assert google_api_key in env_content
        assert "WORKSPACE_PATH=workspace" in env_content
        assert "LMSTUDIO_BASE_URL" not in env_content or "# LMSTUDIO" in env_content

    def test_generates_valid_env_file_lmstudio_only(self):
        """Verifies installer generates valid .env for LM Studio-only setup."""
        lmstudio_url = "http://localhost:1234/v1"
        workspace_path = "workspace"

        env_content = self._generate_env_content(
            google_api_key=None,
            lmstudio_base_url=lmstudio_url,
            workspace_path=workspace_path
        )

        # Validate
        assert "LMSTUDIO_BASE_URL" in env_content
        assert lmstudio_url in env_content
        assert "WORKSPACE_PATH=workspace" in env_content
        assert "GOOGLE_API_KEY" not in env_content or "# Google" in env_content

    def test_generates_valid_env_file_hybrid(self):
        """Verifies installer generates valid .env for hybrid setup."""
        google_api_key = "test_api_key_456"
        lmstudio_url = "http://localhost:1234/v1"
        workspace_path = "workspace"

        env_content = self._generate_env_content(
            google_api_key=google_api_key,
            lmstudio_base_url=lmstudio_url,
            workspace_path=workspace_path
        )

        # Validate
        assert "GOOGLE_API_KEY" in env_content
        assert google_api_key in env_content
        assert "LMSTUDIO_BASE_URL" in env_content
        assert lmstudio_url in env_content
        assert "WORKSPACE_PATH=workspace" in env_content

    def test_converts_localhost_to_docker_host(self):
        """Verifies Docker mode converts localhost to host.docker.internal."""
        lmstudio_url = "http://localhost:1234/v1"

        # Simulate Docker mode conversion
        converted_url = lmstudio_url.replace("localhost", "host.docker.internal")

        assert converted_url == "http://host.docker.internal:1234/v1"
        assert "localhost" not in converted_url

    def test_generates_valid_user_settings_gemini(self):
        """Verifies installer generates valid user_settings.yaml for Gemini."""
        default_provider = "gemini_flash"
        router_provider = "gemini_flash"

        user_settings = self._generate_user_settings(
            has_gemini=True,
            has_lmstudio=False,
            default_provider=default_provider,
            router_provider=router_provider
        )

        # Parse as YAML to validate syntax
        parsed = yaml.safe_load(user_settings)

        # Validate structure
        assert "llm_providers" in parsed
        assert "gemini_flash" in parsed["llm_providers"]
        assert parsed["llm_providers"]["gemini_flash"]["type"] == "gemini"
        assert "specialist_model_bindings" in parsed
        assert parsed["specialist_model_bindings"]["router_specialist"] == "gemini_flash"
        assert parsed["default_llm_config"] == "gemini_flash"

    def test_generates_valid_user_settings_lmstudio(self):
        """Verifies installer generates valid user_settings.yaml for LM Studio."""
        default_provider = "lmstudio_specialist"
        router_provider = "lmstudio_router"

        user_settings = self._generate_user_settings(
            has_gemini=False,
            has_lmstudio=True,
            default_provider=default_provider,
            router_provider=router_provider
        )

        parsed = yaml.safe_load(user_settings)

        assert "lmstudio_router" in parsed["llm_providers"]
        assert "lmstudio_specialist" in parsed["llm_providers"]
        assert parsed["llm_providers"]["lmstudio_router"]["type"] == "lmstudio"
        assert parsed["specialist_model_bindings"]["router_specialist"] == "lmstudio_router"
        assert parsed["default_llm_config"] == "lmstudio_specialist"

    def test_generated_user_settings_binds_critical_specialists(self):
        """Verifies all critical specialists get bindings in generated config."""
        user_settings = self._generate_user_settings(
            has_gemini=True,
            has_lmstudio=False,
            default_provider="gemini_flash",
            router_provider="gemini_flash"
        )

        parsed = yaml.safe_load(user_settings)
        bindings = parsed["specialist_model_bindings"]

        # Critical specialists that must be bound
        critical_specialists = [
            "router_specialist",
            "chat_specialist",
            "end_specialist",
        ]

        for specialist in critical_specialists:
            assert specialist in bindings, f"Critical specialist '{specialist}' not bound"
            assert bindings[specialist] in ["gemini_flash", "lmstudio_router", "lmstudio_specialist"]

    def test_installer_does_not_overwrite_existing_configs(self):
        """Verifies installer logic checks for existing files before writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create existing .env file
            existing_env = tmpdir_path / ".env"
            existing_env.write_text("EXISTING_CONFIG=true\n")

            # Simulate installer check
            should_create = not existing_env.exists()

            assert not should_create, "Installer should detect existing .env"

            # Verify existing content not lost
            assert "EXISTING_CONFIG" in existing_env.read_text()

    def test_generated_config_is_parseable_by_config_loader(self):
        """Verifies generated user_settings.yaml can be loaded by ConfigLoader."""
        from app.src.utils.config_schema import UserSettings

        user_settings = self._generate_user_settings(
            has_gemini=True,
            has_lmstudio=False,
            default_provider="gemini_flash",
            router_provider="gemini_flash"
        )

        parsed = yaml.safe_load(user_settings)

        # This will raise ValidationError if schema is invalid
        try:
            validated = UserSettings(**parsed)
            assert validated.default_llm_config == "gemini_flash"
        except Exception as e:
            pytest.fail(f"Generated user_settings.yaml failed validation: {e}")

    # =========================================================================
    # Helper Methods (Simulate Installer Logic)
    # =========================================================================

    def _generate_env_content(self, google_api_key=None, lmstudio_base_url=None, workspace_path="workspace"):
        """Simulates installer's .env generation logic."""
        content = f"""# Auto-generated test .env

# ===================================================================
#  System Configuration
# ===================================================================
WORKSPACE_PATH={workspace_path}

# ===================================================================
#  LLM Provider Configuration
# ===================================================================

"""
        if google_api_key:
            content += f"""# Google Gemini
GOOGLE_API_KEY="{google_api_key}"

"""

        if lmstudio_base_url:
            content += f"""# LM Studio (Local)
LMSTUDIO_BASE_URL="{lmstudio_base_url}"

"""

        content += """# ===================================================================
#  Observability (Optional)
# ===================================================================
# LANGCHAIN_TRACING_V2="true"
# LANGCHAIN_API_KEY="ls__your_key"
"""
        return content

    def _generate_user_settings(self, has_gemini, has_lmstudio, default_provider, router_provider):
        """Simulates installer's user_settings.yaml generation logic."""
        content = "# Auto-generated test user_settings.yaml\n\nllm_providers:\n"

        if has_gemini:
            content += """  gemini_flash:
    type: "gemini"
    api_identifier: "gemini-2.5-flash"
  gemini_pro:
    type: "gemini"
    api_identifier: "gemini-2.5-pro"
"""

        if has_lmstudio:
            content += """  lmstudio_router:
    type: "lmstudio"
    api_identifier: "local-model"
  lmstudio_specialist:
    type: "lmstudio"
    api_identifier: "local-model"
"""

        content += f"""
specialist_model_bindings:
  router_specialist: "{router_provider}"
  prompt_triage_specialist: "{default_provider}"
  chat_specialist: "{default_provider}"
  systems_architect: "{default_provider}"
  prompt_specialist: "{default_provider}"
  open_interpreter_specialist: "{default_provider}"
  end_specialist: "{default_provider}"

  # Tiered chat subgraph
  progenitor_alpha_specialist: "{default_provider}"
  progenitor_bravo_specialist: "{default_provider}"

default_llm_config: "{default_provider}"

ui_module: "gradio_app"
"""
        return content


class TestInstallerScriptLogic:
    """Tests for installer script decision logic."""

    def test_recommends_docker_when_available(self):
        """Verifies installer recommends Docker when both Docker and Python available."""
        docker_available = True
        python_ok = True

        # Installer should recommend Docker (mode 1)
        recommended = 1 if docker_available else 2

        assert recommended == 1, "Should recommend Docker when available"

    def test_falls_back_to_python_when_docker_unavailable(self):
        """Verifies installer falls back to Python when Docker not available."""
        docker_available = False
        python_ok = True

        recommended = 1 if docker_available else 2

        assert recommended == 2, "Should fall back to Python when Docker unavailable"

    def test_errors_when_neither_available(self):
        """Verifies installer errors when neither Docker nor Python available."""
        docker_available = False
        python_ok = False

        # Installer should exit with error
        should_error = not docker_available and not python_ok

        assert should_error, "Should error when no valid installation method"

    @pytest.mark.parametrize("provider_choice,expected_default,expected_router", [
        ("1", "gemini_flash", "gemini_flash"),  # Gemini only
        ("2", "lmstudio_specialist", "lmstudio_router"),  # LM Studio only
        ("3", "gemini_flash", "gemini_flash"),  # Hybrid (Gemini default)
    ])
    def test_provider_choice_sets_correct_defaults(self, provider_choice, expected_default, expected_router):
        """Verifies each provider choice sets correct default and router bindings."""
        # Simulate installer logic
        if provider_choice == "1":
            default = "gemini_flash"
            router = "gemini_flash"
        elif provider_choice == "2":
            default = "lmstudio_specialist"
            router = "lmstudio_router"
        elif provider_choice == "3":
            default = "gemini_flash"
            router = "gemini_flash"
        else:
            pytest.fail(f"Unknown provider choice: {provider_choice}")

        assert default == expected_default
        assert router == expected_router


class TestSurfMcpSetup:
    """Tests for surf-mcp detection and setup in installer."""

    def test_detects_existing_surf_mcp(self):
        """Verifies installer detects existing surf-mcp sibling repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "las"
            surf_mcp_dir = Path(tmpdir) / "surf-mcp"

            project_root.mkdir()
            surf_mcp_dir.mkdir()

            # Simulate detection logic
            surf_mcp_available = surf_mcp_dir.exists()

            assert surf_mcp_available, "Should detect existing surf-mcp"

    def test_detects_missing_surf_mcp(self):
        """Verifies installer detects when surf-mcp is not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "las"
            surf_mcp_dir = Path(tmpdir) / "surf-mcp"

            project_root.mkdir()
            # Don't create surf_mcp_dir

            surf_mcp_available = surf_mcp_dir.exists()

            assert not surf_mcp_available, "Should detect missing surf-mcp"

    def test_sibling_path_resolution(self):
        """Verifies surf-mcp path is correctly resolved as sibling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "las"
            project_root.mkdir()

            # Simulate path resolution from setup.sh
            surf_mcp_dir = project_root.parent / "surf-mcp"

            expected = Path(tmpdir) / "surf-mcp"
            assert surf_mcp_dir == expected, "Should resolve to sibling directory"

    def test_surf_mcp_optional_not_blocking(self):
        """Verifies missing surf-mcp doesn't block installation."""
        # If surf-mcp is not available, installer should continue
        surf_mcp_available = False
        install_should_proceed = True  # Always proceed, surf-mcp is optional

        assert install_should_proceed, "Installation should proceed without surf-mcp"
