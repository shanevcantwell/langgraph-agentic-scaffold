"""
Tests for MCP service installation script (scripts/add_mcp_service.py).

Tests cover:
- Registry loading and service info retrieval
- Prerequisite validation (Docker, templates)
- Docker image building
- Atomic config.yaml updates with rollback capability
- .env.example updates
- Full installation workflow
"""
import pytest
import shutil
import subprocess
import tempfile
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Import the installer class
import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.add_mcp_service import McpServiceInstaller


@pytest.fixture
def temp_project_root(tmp_path):
    """Create temporary project structure for testing."""
    # Create directory structure
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    templates_dir = tmp_path / "docker" / "templates"
    templates_dir.mkdir(parents=True)

    services_dir = tmp_path / "docker" / "mcp-services"
    services_dir.mkdir(parents=True)

    # Create mock registry
    registry = {
        "available_servers": {
            "test-service": {
                "source": "npm",
                "package": "@test/server-test",
                "dockerfile_template": "node-mcp",
                "env_vars": ["TEST_API_KEY"],
                "args": [],
                "volumes": [],
                "description": "Test service for unit tests"
            },
            "simple-service": {
                "source": "npm",
                "package": "@test/simple",
                "dockerfile_template": "node-mcp",
                "env_vars": [],
                "args": [],
                "volumes": [],
                "description": "Simple service without env vars"
            }
        }
    }

    registry_path = config_dir / "mcp_registry.yaml"
    with open(registry_path, "w") as f:
        yaml.dump(registry, f)

    # Create mock template
    template_path = templates_dir / "node-mcp.Dockerfile"
    template_path.write_text("FROM node:lts-alpine\nRUN echo 'test'")

    # Create mock config.yaml
    config_path = tmp_path / "config.yaml"
    config_path.write_text("mcp:\n  external_mcp:\n    enabled: true\n    services: {}")

    # Create mock .env.example
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text("# Existing env vars\nEXISTING_VAR=value\n")

    return tmp_path


@pytest.fixture
def installer(temp_project_root):
    """Create McpServiceInstaller instance with temp project root."""
    return McpServiceInstaller(temp_project_root)


def test_list_available_servers(installer):
    """Test listing all available MCP servers from registry."""
    servers = installer.list_available_servers()

    assert len(servers) == 2
    assert "test-service" in servers
    assert "simple-service" in servers


def test_get_server_info_existing(installer):
    """Test retrieving service info for existing service."""
    info = installer.get_server_info("test-service")

    assert info is not None
    assert info["source"] == "npm"
    assert info["package"] == "@test/server-test"
    assert info["dockerfile_template"] == "node-mcp"
    assert "TEST_API_KEY" in info["env_vars"]
    assert info["description"] == "Test service for unit tests"


def test_get_server_info_nonexistent(installer):
    """Test retrieving service info for non-existent service."""
    info = installer.get_server_info("nonexistent-service")

    assert info is None


@patch("scripts.add_mcp_service.subprocess.run")
def test_validate_prerequisites_success(mock_run, installer):
    """Test prerequisite validation when all checks pass."""
    # Mock successful Docker check
    mock_run.return_value = MagicMock(returncode=0)

    service_info = {
        "dockerfile_template": "node-mcp"
    }

    errors = installer.validate_prerequisites(service_info)

    assert len(errors) == 0
    mock_run.assert_called_once_with(
        ["docker", "ps"],
        check=True,
        capture_output=True,
        text=True
    )


@patch("scripts.add_mcp_service.subprocess.run")
def test_validate_prerequisites_docker_not_running(mock_run, installer):
    """Test prerequisite validation when Docker is not running."""
    # Mock Docker check failure
    mock_run.side_effect = subprocess.CalledProcessError(1, "docker ps")

    service_info = {
        "dockerfile_template": "node-mcp"
    }

    errors = installer.validate_prerequisites(service_info)

    assert len(errors) == 1
    assert "Docker is not running" in errors[0]


@patch("scripts.add_mcp_service.subprocess.run")
def test_validate_prerequisites_missing_template(mock_run, installer):
    """Test prerequisite validation when template doesn't exist."""
    # Mock successful Docker check
    mock_run.return_value = MagicMock(returncode=0)

    service_info = {
        "dockerfile_template": "nonexistent-template"
    }

    errors = installer.validate_prerequisites(service_info)

    assert len(errors) == 1
    assert "Dockerfile template 'nonexistent-template' not found" in errors[0]


@patch("scripts.add_mcp_service.subprocess.run")
def test_build_docker_image_success(mock_run, installer):
    """Test successful Docker image build."""
    # Mock successful Docker build
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    service_info = {
        "package": "@test/server-test",
        "dockerfile_template": "node-mcp"
    }

    result = installer.build_docker_image("test-service", service_info)

    assert result is True

    # Verify Dockerfile was created
    service_dir = installer.services_dir / "test-service"
    assert service_dir.exists()
    assert (service_dir / "Dockerfile").exists()

    # Verify docker build command was called
    build_call = mock_run.call_args
    assert build_call[0][0] == ["docker", "build",
                                 "--build-arg", "NPM_PACKAGE=@test/server-test",
                                 "-f", str(service_dir / "Dockerfile"),
                                 "-t", "mcp/test-service",
                                 "."]


@patch("scripts.add_mcp_service.subprocess.run")
def test_build_docker_image_failure(mock_run, installer):
    """Test Docker image build failure."""
    # Mock failed Docker build
    mock_run.return_value = MagicMock(
        returncode=1,
        stderr="Error: Build failed"
    )

    service_info = {
        "package": "@test/server-test",
        "dockerfile_template": "node-mcp"
    }

    result = installer.build_docker_image("test-service", service_info)

    assert result is False


def test_update_config_yaml_new_service(installer):
    """Test adding new MCP service to config.yaml."""
    service_info = {
        "package": "@test/server-test",
        "env_vars": ["TEST_API_KEY"],
        "volumes": [],
        "args": ["--verbose"]
    }

    result = installer.update_config_yaml("test-service", service_info, required=False)

    assert result is True

    # Verify config was updated
    with open(installer.config_path) as f:
        config = yaml.safe_load(f)

    assert "test-service" in config["mcp"]["external_mcp"]["services"]
    service_config = config["mcp"]["external_mcp"]["services"]["test-service"]

    assert service_config["enabled"] is True
    assert service_config["required"] is False
    assert service_config["command"] == "docker"
    assert "run" in service_config["args"]
    assert "-i" in service_config["args"]
    assert "--rm" in service_config["args"]
    assert "mcp/test-service" in service_config["args"]
    assert "--verbose" in service_config["args"]

    # Verify backup was created
    backup_path = installer.config_path.with_suffix(".yaml.backup")
    assert backup_path.exists()


def test_update_config_yaml_with_env_vars(installer):
    """Test config.yaml update includes environment variables."""
    service_info = {
        "package": "@test/server-test",
        "env_vars": ["API_KEY", "SECRET_TOKEN"],
        "volumes": [],
        "args": []
    }

    result = installer.update_config_yaml("test-service", service_info)

    assert result is True

    with open(installer.config_path) as f:
        config = yaml.safe_load(f)

    service_config = config["mcp"]["external_mcp"]["services"]["test-service"]

    # Verify environment variables are in args
    assert "-e" in service_config["args"]
    assert "API_KEY=${API_KEY}" in service_config["args"]
    assert "SECRET_TOKEN=${SECRET_TOKEN}" in service_config["args"]


def test_update_config_yaml_with_volumes(installer):
    """Test config.yaml update includes volume mounts."""
    service_info = {
        "package": "@test/server-test",
        "env_vars": [],
        "volumes": ["${WORKSPACE_PATH}:/projects"],
        "args": []
    }

    result = installer.update_config_yaml("test-service", service_info)

    assert result is True

    with open(installer.config_path) as f:
        config = yaml.safe_load(f)

    service_config = config["mcp"]["external_mcp"]["services"]["test-service"]

    # Verify volume is in args
    assert "-v" in service_config["args"]
    assert "${WORKSPACE_PATH}:/projects" in service_config["args"]


def test_update_config_yaml_required_flag(installer):
    """Test config.yaml update respects required flag."""
    service_info = {
        "package": "@test/server-test",
        "env_vars": [],
        "volumes": [],
        "args": []
    }

    result = installer.update_config_yaml("test-service", service_info, required=True)

    assert result is True

    with open(installer.config_path) as f:
        config = yaml.safe_load(f)

    service_config = config["mcp"]["external_mcp"]["services"]["test-service"]
    assert service_config["required"] is True


def test_update_config_yaml_atomic_write(installer):
    """Test config.yaml update uses atomic temp file + rename pattern."""
    service_info = {
        "package": "@test/server-test",
        "env_vars": [],
        "volumes": [],
        "args": []
    }

    # Verify temp file is created and renamed
    with patch("pathlib.Path.replace") as mock_replace:
        result = installer.update_config_yaml("test-service", service_info)

        assert result is True
        mock_replace.assert_called_once_with(installer.config_path)


def test_update_env_example_new_vars(installer):
    """Test adding environment variables to .env.example."""
    service_info = {
        "env_vars": ["NEW_API_KEY", "NEW_SECRET"],
        "description": "Test service API key"
    }

    result = installer.update_env_example(service_info)

    assert result is True

    # Verify .env.example was updated
    with open(installer.env_example_path) as f:
        content = f.read()

    assert "NEW_API_KEY" in content
    assert "NEW_SECRET" in content
    assert "MCP SERVICE CONFIGURATION" in content


def test_update_env_example_no_vars(installer):
    """Test .env.example update with no environment variables."""
    service_info = {
        "env_vars": []
    }

    result = installer.update_env_example(service_info)

    assert result is True

    # Verify .env.example was not modified
    with open(installer.env_example_path) as f:
        content = f.read()

    assert content == "# Existing env vars\nEXISTING_VAR=value\n"


def test_update_env_example_creates_section(installer):
    """Test .env.example update creates MCP section if missing."""
    # Start with .env.example without MCP section
    installer.env_example_path.write_text("# Existing vars\n")

    service_info = {
        "env_vars": ["TEST_KEY"],
        "description": "Test API key"
    }

    result = installer.update_env_example(service_info)

    assert result is True

    with open(installer.env_example_path) as f:
        content = f.read()

    assert "MCP SERVICE CONFIGURATION" in content
    assert "TEST_KEY" in content


@patch("scripts.add_mcp_service.subprocess.run")
def test_install_service_success(mock_run, installer):
    """Test full service installation workflow."""
    # Mock successful Docker check and build
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    result = installer.install_service("simple-service", required=False, auto_restart=False)

    assert result is True

    # Verify service was added to config
    with open(installer.config_path) as f:
        config = yaml.safe_load(f)

    assert "simple-service" in config["mcp"]["external_mcp"]["services"]


@patch("scripts.add_mcp_service.subprocess.run")
def test_install_service_nonexistent(mock_run, installer):
    """Test installation fails for non-existent service."""
    result = installer.install_service("nonexistent-service")

    assert result is False


@patch("scripts.add_mcp_service.subprocess.run")
def test_install_service_prerequisite_failure(mock_run, installer):
    """Test installation fails when prerequisites not met."""
    # Mock Docker check failure
    mock_run.side_effect = subprocess.CalledProcessError(1, "docker ps")

    result = installer.install_service("test-service")

    assert result is False


@patch("scripts.add_mcp_service.subprocess.run")
def test_install_service_with_auto_restart(mock_run, installer):
    """Test installation with auto-restart option."""
    # Mock successful Docker build and restart
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    result = installer.install_service("simple-service", auto_restart=True)

    assert result is True

    # Verify docker compose restart was called
    restart_calls = [call for call in mock_run.call_args_list
                     if "docker" in call[0][0] and "compose" in call[0][0] and "restart" in call[0][0]]
    assert len(restart_calls) >= 1


@patch("scripts.add_mcp_service.subprocess.run")
def test_restart_application(mock_run, installer):
    """Test Docker Compose application restart."""
    mock_run.return_value = MagicMock(returncode=0)

    installer.restart_application()

    mock_run.assert_called_once_with(
        ["docker", "compose", "restart", "app"],
        cwd=str(installer.project_root),
        check=True
    )


@patch("scripts.add_mcp_service.subprocess.run")
def test_restart_application_failure(mock_run, installer):
    """Test application restart handles failures gracefully."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "docker compose restart")

    # Should not raise exception
    installer.restart_application()
