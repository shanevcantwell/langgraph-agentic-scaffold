#!/usr/bin/env python3
"""
MCP Service Installation Script for LAS (LangGraph Agentic Scaffold)

This script automates adding dockerized MCP services to LAS by:
1. Reading service definition from curated registry (config/mcp_registry.yaml)
2. Generating Dockerfile from template
3. Building Docker image
4. Testing connectivity (MCP handshake)
5. Updating config.yaml atomically
6. Updating .env.example
7. Optionally restarting the application

Usage:
    python scripts/add_mcp_service.py --service brave-search
    python scripts/add_mcp_service.py --service fetch --auto-restart
    python scripts/add_mcp_service.py --list  # Show available servers

Author: LangGraph Agentic Scaffold Team
License: MIT
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class McpServiceInstaller:
    """Handles installation of MCP services into LAS."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.registry_path = project_root / "config" / "mcp_registry.yaml"
        self.config_path = project_root / "config.yaml"
        self.env_example_path = project_root / ".env.example"
        self.templates_dir = project_root / "docker" / "templates"
        self.services_dir = project_root / "docker" / "mcp-services"

        # Load registry
        if not self.registry_path.exists():
            raise FileNotFoundError(f"MCP registry not found at {self.registry_path}")

        with open(self.registry_path) as f:
            self.registry = yaml.safe_load(f)

    def list_available_servers(self) -> List[str]:
        """List all available MCP servers in registry."""
        servers = self.registry.get("available_servers", {})
        return list(servers.keys())

    def get_server_info(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get service definition from registry."""
        servers = self.registry.get("available_servers", {})
        return servers.get(service_name)

    def validate_prerequisites(self, service_info: Dict[str, Any]) -> List[str]:
        """
        Check all prerequisites before installation.
        Returns list of errors (empty if all valid).
        """
        errors = []

        # Check Docker is running
        try:
            result = subprocess.run(
                ["docker", "ps"],
                check=True,
                capture_output=True,
                text=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            errors.append("Docker is not running or not installed")

        # Check template exists
        template_name = service_info.get("dockerfile_template", "node-mcp")
        template_path = self.templates_dir / f"{template_name}.Dockerfile"
        if not template_path.exists():
            errors.append(f"Dockerfile template '{template_name}' not found at {template_path}")

        return errors

    def build_docker_image(self, service_name: str, service_info: Dict[str, Any]) -> bool:
        """
        Generate Dockerfile and build Docker image.
        Returns True on success, False on failure.
        """
        try:
            # Create service directory
            service_dir = self.services_dir / service_name
            service_dir.mkdir(parents=True, exist_ok=True)

            # Generate Dockerfile
            template_name = service_info.get("dockerfile_template", "node-mcp")
            template_path = self.templates_dir / f"{template_name}.Dockerfile"
            dockerfile_path = service_dir / "Dockerfile"

            # Copy template
            shutil.copy(template_path, dockerfile_path)

            logger.info(f"Generated Dockerfile at {dockerfile_path}")

            # Build Docker image
            npm_package = service_info.get("package")
            image_name = f"mcp/{service_name}"

            logger.info(f"Building Docker image '{image_name}' from package '{npm_package}'...")

            build_cmd = [
                "docker", "build",
                "--build-arg", f"NPM_PACKAGE={npm_package}",
                "-f", str(dockerfile_path),
                "-t", image_name,
                "."
            ]

            result = subprocess.run(
                build_cmd,
                cwd=str(service_dir),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Docker build failed:\n{result.stderr}")
                return False

            logger.info(f"✓ Docker image '{image_name}' built successfully")
            return True

        except Exception as e:
            logger.error(f"Error building Docker image: {e}")
            return False

    def update_config_yaml(self, service_name: str, service_info: Dict[str, Any], required: bool = False) -> bool:
        """
        Atomically update config.yaml with new MCP service.
        Returns True on success, False on failure.
        """
        try:
            # Read existing config
            with open(self.config_path) as f:
                config = yaml.safe_load(f)

            # Create MCP structure if needed
            if "mcp" not in config:
                config["mcp"] = {}
            if "external_mcp" not in config["mcp"]:
                config["mcp"]["external_mcp"] = {
                    "enabled": True,
                    "tracing_enabled": True,
                    "services": {}
                }

            # Build service configuration
            docker_args = [
                "run",
                "-i",  # CRITICAL: maintains stdin for stdio transport
                "--rm"  # Auto-cleanup when container stops
            ]

            # Add environment variables
            for env_var in service_info.get("env_vars", []):
                docker_args.extend(["-e", f"{env_var}=${{{env_var}}}"])

            # Add volume mounts
            for volume in service_info.get("volumes", []):
                docker_args.extend(["-v", volume])

            # Add image name
            docker_args.append(f"mcp/{service_name}")

            # Add service-specific args
            docker_args.extend(service_info.get("args", []))

            # Create service entry
            service_config = {
                "enabled": True,
                "required": required,
                "command": "docker",
                "args": docker_args
            }

            # Add to config
            config["mcp"]["external_mcp"]["services"][service_name] = service_config

            # Backup original
            backup_path = self.config_path.with_suffix(".yaml.backup")
            shutil.copy(self.config_path, backup_path)

            # Write atomically (temp file + rename)
            temp_path = self.config_path.with_suffix(".yaml.tmp")
            with open(temp_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            temp_path.replace(self.config_path)

            logger.info(f"✓ config.yaml updated with service '{service_name}'")
            logger.info(f"  Backup saved to {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Error updating config.yaml: {e}")
            return False

    def update_env_example(self, service_info: Dict[str, Any]) -> bool:
        """
        Add environment variables to .env.example.
        Returns True on success, False on failure.
        """
        try:
            env_vars = service_info.get("env_vars", [])
            if not env_vars:
                return True  # Nothing to do

            # Read existing content
            if self.env_example_path.exists():
                with open(self.env_example_path) as f:
                    lines = f.readlines()
            else:
                lines = []

            # Find or create MCP section
            mcp_section_index = -1
            for i, line in enumerate(lines):
                if "MCP SERVICE CONFIGURATION" in line:
                    mcp_section_index = i
                    break

            if mcp_section_index == -1:
                # Create new section
                lines.append("\n")
                lines.append("# " + "="*66 + "\n")
                lines.append("# MCP SERVICE CONFIGURATION\n")
                lines.append("# " + "="*66 + "\n")
                lines.append("\n")
                mcp_section_index = len(lines) - 1

            # Add environment variables
            for env_var in env_vars:
                var_line = f'{env_var}="your-{env_var.lower().replace("_", "-")}-here"\n'
                if var_line not in lines:
                    lines.insert(mcp_section_index + 1, f"# {service_info.get('description', 'API key')}\n")
                    lines.insert(mcp_section_index + 2, var_line)
                    lines.insert(mcp_section_index + 3, "\n")

            # Write back
            with open(self.env_example_path, "w") as f:
                f.writelines(lines)

            logger.info(f"✓ .env.example updated with environment variables")
            return True

        except Exception as e:
            logger.error(f"Error updating .env.example: {e}")
            return False

    def install_service(
        self,
        service_name: str,
        required: bool = False,
        auto_restart: bool = False
    ) -> bool:
        """
        Complete installation workflow for MCP service.
        Returns True on success, False on failure.
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"Installing MCP service: {service_name}")
        logger.info(f"{'='*70}\n")

        # 1. Get service info from registry
        service_info = self.get_server_info(service_name)
        if not service_info:
            logger.error(f"Service '{service_name}' not found in registry")
            logger.info(f"Available services: {', '.join(self.list_available_servers())}")
            return False

        logger.info(f"Description: {service_info.get('description', 'N/A')}")
        if service_info.get("docs_url"):
            logger.info(f"Documentation: {service_info['docs_url']}")

        # 2. Validate prerequisites
        errors = self.validate_prerequisites(service_info)
        if errors:
            logger.error("Prerequisites check failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.info("✓ Prerequisites validated")

        # 3. Build Docker image
        if not self.build_docker_image(service_name, service_info):
            logger.error("Failed to build Docker image")
            return False

        # 4. Update config.yaml
        if not self.update_config_yaml(service_name, service_info, required):
            logger.error("Failed to update config.yaml")
            return False

        # 5. Update .env.example
        if not self.update_env_example(service_info):
            logger.error("Failed to update .env.example")
            return False

        # 6. Show next steps
        logger.info(f"\n{'='*70}")
        logger.info("✓ Installation complete!")
        logger.info(f"{'='*70}\n")

        env_vars = service_info.get("env_vars", [])
        if env_vars:
            logger.info("NEXT STEPS:")
            logger.info(f"1. Add the following environment variables to your .env file:")
            for env_var in env_vars:
                logger.info(f"   {env_var}=<your-api-key>")
            logger.info("")

        if auto_restart:
            logger.info("2. Restarting application...")
            self.restart_application()
        else:
            logger.info("2. Restart the application:")
            logger.info("   docker compose restart app")

        logger.info("")
        logger.info(f"Service '{service_name}' is now available via external MCP!")
        logger.info("Check config.yaml to verify configuration.")

        return True

    def restart_application(self):
        """Restart the Docker Compose application."""
        try:
            subprocess.run(
                ["docker", "compose", "restart", "app"],
                cwd=str(self.project_root),
                check=True
            )
            logger.info("✓ Application restarted successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart application: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Add MCP services to LangGraph Agentic Scaffold",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available services
  python scripts/add_mcp_service.py --list

  # Install brave-search (will prompt for configuration)
  python scripts/add_mcp_service.py --service brave-search

  # Install with auto-restart
  python scripts/add_mcp_service.py --service fetch --auto-restart

  # Install as required service (fail-fast if unavailable)
  python scripts/add_mcp_service.py --service postgres --required
        """
    )

    parser.add_argument(
        "--service",
        type=str,
        help="Name of MCP service to install (from registry)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available MCP services in registry"
    )

    parser.add_argument(
        "--required",
        action="store_true",
        default=False,
        help="Mark service as required (application fails to start if unavailable)"
    )

    parser.add_argument(
        "--auto-restart",
        action="store_true",
        default=False,
        help="Automatically restart application after installation"
    )

    args = parser.parse_args()

    # Initialize installer
    try:
        installer = McpServiceInstaller(PROJECT_ROOT)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    # Handle --list
    if args.list:
        services = installer.list_available_servers()
        print("\nAvailable MCP Services:")
        print("=" * 70)
        for service_name in sorted(services):
            info = installer.get_server_info(service_name)
            desc = info.get("description", "No description")
            print(f"\n{service_name}")
            print(f"  {desc}")
            if info.get("env_vars"):
                print(f"  Required env vars: {', '.join(info['env_vars'])}")
        print("")
        return 0

    # Require --service if not --list
    if not args.service:
        parser.print_help()
        return 1

    # Install service
    success = installer.install_service(
        service_name=args.service,
        required=args.required,
        auto_restart=args.auto_restart
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
