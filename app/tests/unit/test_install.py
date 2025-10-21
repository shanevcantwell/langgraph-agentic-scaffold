"""Unit tests for the install.sh script."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class TestInstallScript(unittest.TestCase):
    """Test the install.sh script."""

    def setUp(self):
        """Set up a temporary directory for testing."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="install_test_"))
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up after each test."""
        os.chdir(self.original_dir)
        if self.temp_dir.exists():
            # Remove the virtual environment and temp directory
            venv_path = self.temp_dir / ".venv_agents"
            if venv_path.exists():
                # On Windows, we need to use rmdir /s /q
                if sys.platform == "win32":
                    subprocess.run(["rmdir", "/s", "/q", str(venv_path)], check=False)
                else:
                    subprocess.run(["rm", "-rf", str(venv_path)], check=False)
            # Remove the temp directory
            subprocess.run(["rm", "-rf", str(self.temp_dir)], check=False)

    def test_install_script_creates_venv_and_installs_pytest(self):
        """Test that install.sh creates a virtual environment and installs pytest."""
        # Copy the install.sh script to the temp directory
        install_script = Path("install.sh")
        install_script.write_text(Path("../scripts/install.sh").read_text())

        # Make it executable
        install_script.chmod(0o755)

        # Run install.sh
        result = subprocess.run(
            [str(install_script)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check that it succeeded
        self.assertEqual(result.returncode, 0, f"install.sh failed: {result.stderr}")

        # Check that .venv_agents was created
        venv_path = self.temp_dir / ".venv_agents"
        self.assertTrue(venv_path.exists(), "Virtual environment not created")

        # Check that pytest is installed
        pip_path = venv_path / "bin" / "pip"
        result = subprocess.run(
            [str(pip_path), "list", "--format=freeze"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertIn("pytest", result.stdout, "pytest not installed in virtual environment")

        # Check that pytest runs
        pytest_path = venv_path / "bin" / "pytest"
        result = subprocess.run(
            [str(pytest_path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, "pytest --version failed")

if __name__ == "__main__":
    unittest.main()