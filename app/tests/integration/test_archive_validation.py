"""
Archive and Log Validation Tests

These tests validate the runtime artifacts produced by completed workflows:
- Archive zip files in ./logs/archive/
- Server logs in ./logs/agentic_server.log
- Manifest schema compliance
- Routing history patterns

These tests use actual archives from real workflow runs, providing
regression testing against the live system output.
"""

import json
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import pytest


# =============================================================================
# FIXTURES
# =============================================================================

ARCHIVE_DIR = Path("/app/logs/archive")
LOG_FILE = Path("/app/logs/agentic_server.log")


@pytest.fixture
def archive_dir() -> Path:
    """Return the archive directory path."""
    return ARCHIVE_DIR


@pytest.fixture
def latest_archive(archive_dir) -> Optional[zipfile.ZipFile]:
    """Return the most recent archive zip file."""
    if not archive_dir.exists():
        pytest.skip("Archive directory does not exist")

    archives = sorted(archive_dir.glob("run_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not archives:
        pytest.skip("No archive files found")

    return zipfile.ZipFile(archives[0], 'r')


@pytest.fixture
def recent_archives(archive_dir, count: int = 10) -> List[zipfile.ZipFile]:
    """Return the N most recent archive zip files."""
    if not archive_dir.exists():
        pytest.skip("Archive directory does not exist")

    archives = sorted(archive_dir.glob("run_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [zipfile.ZipFile(a, 'r') for a in archives[:count]]


@pytest.fixture
def server_log() -> Optional[str]:
    """Return the server log content."""
    if not LOG_FILE.exists():
        pytest.skip("Server log file does not exist")
    return LOG_FILE.read_text()


def get_manifest(archive: zipfile.ZipFile) -> Dict[str, Any]:
    """Extract and parse manifest.json from an archive."""
    return json.loads(archive.read("manifest.json"))


# =============================================================================
# ARCHIVE STRUCTURE TESTS
# =============================================================================

@pytest.mark.archive
class TestArchiveStructure:
    """Tests for archive file structure and contents."""

    def test_archive_contains_manifest(self, latest_archive):
        """Verify archive contains a manifest.json file."""
        assert "manifest.json" in latest_archive.namelist()

    def test_archive_contains_report(self, latest_archive):
        """Verify archive contains a report.md file."""
        assert "report.md" in latest_archive.namelist()

    def test_manifest_is_valid_json(self, latest_archive):
        """Verify manifest.json is valid JSON."""
        manifest_content = latest_archive.read("manifest.json")
        manifest = json.loads(manifest_content)
        assert isinstance(manifest, dict)

    def test_archive_files_are_readable(self, latest_archive):
        """Verify all files in archive can be read without error."""
        for filename in latest_archive.namelist():
            content = latest_archive.read(filename)
            assert content is not None


# =============================================================================
# MANIFEST SCHEMA TESTS
# =============================================================================

@pytest.mark.archive
class TestManifestSchema:
    """Tests for manifest.json schema compliance."""

    def test_manifest_has_required_fields(self, latest_archive):
        """Verify manifest contains all required fields."""
        manifest = get_manifest(latest_archive)

        required_fields = [
            "timestamp",
            "run_id",
            "routing_history",
            "artifacts",
            "final_response_generated",
            "termination_reason"
        ]

        for field in required_fields:
            assert field in manifest, f"Missing required field: {field}"

    def test_manifest_run_id_is_uuid_format(self, latest_archive):
        """Verify run_id follows UUID format."""
        manifest = get_manifest(latest_archive)
        run_id = manifest["run_id"]

        # UUID format: 8-4-4-4-12 hex characters
        parts = run_id.split("-")
        assert len(parts) == 5, f"Invalid UUID format: {run_id}"
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_manifest_timestamp_is_iso_format(self, latest_archive):
        """Verify timestamp is valid ISO format."""
        manifest = get_manifest(latest_archive)
        timestamp = manifest["timestamp"]

        # Should parse without error
        datetime.fromisoformat(timestamp)

    def test_manifest_routing_history_is_list(self, latest_archive):
        """Verify routing_history is a non-empty list."""
        manifest = get_manifest(latest_archive)

        assert isinstance(manifest["routing_history"], list)
        assert len(manifest["routing_history"]) > 0

    def test_manifest_artifacts_have_required_fields(self, latest_archive):
        """Verify each artifact entry has required fields."""
        manifest = get_manifest(latest_archive)

        required_artifact_fields = [
            "filename",
            "original_key",
            "content_type",
            "size_bytes"
        ]

        for artifact in manifest["artifacts"]:
            for field in required_artifact_fields:
                assert field in artifact, f"Artifact missing field: {field}"

    def test_manifest_artifacts_exist_in_archive(self, latest_archive):
        """Verify all artifacts listed in manifest exist in archive."""
        manifest = get_manifest(latest_archive)
        archive_files = latest_archive.namelist()

        for artifact in manifest["artifacts"]:
            filename = artifact["filename"]
            assert filename in archive_files, f"Artifact not in archive: {filename}"

    def test_manifest_termination_reason_is_valid(self, latest_archive):
        """Verify termination_reason is a recognized value."""
        manifest = get_manifest(latest_archive)

        valid_reasons = ["success", "error", "timeout", "loop_detected", "max_iterations"]
        assert manifest["termination_reason"] in valid_reasons


# =============================================================================
# ROUTING HISTORY PATTERN TESTS
# =============================================================================

@pytest.mark.archive
class TestRoutingPatterns:
    """Tests for expected routing patterns in completed workflows."""

    def test_successful_workflow_ends_properly(self, latest_archive):
        """Verify successful workflows have final_response_generated=True."""
        manifest = get_manifest(latest_archive)

        if manifest["termination_reason"] == "success":
            assert manifest["final_response_generated"] is True

    def test_tiered_chat_has_progenitors(self, archive_dir):
        """Verify tiered chat workflows include progenitor specialists."""
        if not archive_dir.exists():
            pytest.skip("Archive directory does not exist")

        archives = sorted(archive_dir.glob("run_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

        tiered_chat_found = False
        for archive_path in archives[:20]:  # Check last 20 archives
            with zipfile.ZipFile(archive_path, 'r') as archive:
                manifest = get_manifest(archive)
                history = manifest["routing_history"]

                # Look for tiered chat pattern
                if "tiered_synthesizer_specialist" in history:
                    tiered_chat_found = True
                    # If synthesizer ran, both progenitors should have run
                    assert "progenitor_alpha_specialist" in history, \
                        f"Tiered chat missing alpha in {archive_path.name}"
                    assert "progenitor_bravo_specialist" in history, \
                        f"Tiered chat missing bravo in {archive_path.name}"

        if not tiered_chat_found:
            pytest.skip("No tiered chat workflows found in recent archives")

    def test_no_router_in_routing_history(self, latest_archive):
        """Verify router_specialist does not appear in routing_history."""
        manifest = get_manifest(latest_archive)

        # Router is the orchestrator, not a destination - should not be in history
        assert "router_specialist" not in manifest["routing_history"], \
            "Router should not appear in routing history"

    def test_triage_is_entry_point_when_present(self, latest_archive):
        """Verify triage_architect is first when it appears in routing."""
        manifest = get_manifest(latest_archive)
        history = manifest["routing_history"]

        if "triage_architect" in history:
            assert history[0] == "triage_architect", \
                "triage_architect should be first in routing history"


# =============================================================================
# LOG FILE TESTS
# =============================================================================

@pytest.mark.archive
class TestServerLogs:
    """Tests for server log content and patterns."""

    def test_log_file_exists(self):
        """Verify server log file exists."""
        assert LOG_FILE.exists(), "Server log file does not exist"

    def test_no_unhandled_exceptions_in_recent_logs(self, server_log):
        """Check for unhandled exceptions in recent log entries."""
        # Get last 100KB of logs (recent activity)
        recent_logs = server_log[-100000:] if len(server_log) > 100000 else server_log

        # Look for Python traceback indicators
        critical_patterns = [
            "Traceback (most recent call last)",
            "CRITICAL",
        ]

        for pattern in critical_patterns:
            if pattern in recent_logs:
                # Extract context around the error
                idx = recent_logs.find(pattern)
                context = recent_logs[max(0, idx-200):idx+500]

                # Allow certain expected errors
                expected_errors = [
                    "test_",  # Test-related
                    "MCP invocation error",  # Expected MCP errors in tests
                    "expected error",  # Intentional test errors
                    "CRITICAL:",  # Prompt text (e.g., "CRITICAL: Satisfy Dependency...")
                    "HIGHEST PRIORITY",  # Prompt instructions
                ]

                if not any(expected in context for expected in expected_errors):
                    pytest.fail(f"Unexpected {pattern} in logs:\n{context[:500]}")

    def test_successful_startup_in_logs(self, server_log):
        """Verify server started successfully."""
        startup_indicators = [
            "Started server process",
            "Configuration loaded, validated, and merged successfully",
        ]

        for indicator in startup_indicators:
            assert indicator in server_log, f"Missing startup indicator: {indicator}"

    def test_specialists_initialized_in_logs(self, server_log):
        """Verify critical specialists were initialized."""
        # Check full log since startup messages are at the beginning
        critical_specialists = [
            "router_specialist",
            "triage_architect",
            "end_specialist",
        ]

        for specialist in critical_specialists:
            pattern = f"Successfully instantiated specialist: {specialist}"
            assert pattern in server_log, f"Specialist not initialized: {specialist}"


# =============================================================================
# ARCHIVE CONSISTENCY TESTS
# =============================================================================

@pytest.mark.archive
class TestArchiveConsistency:
    """Tests for consistency across multiple archives."""

    def test_recent_archives_all_have_valid_manifests(self, archive_dir):
        """Verify all recent archives have valid manifest files."""
        if not archive_dir.exists():
            pytest.skip("Archive directory does not exist")

        archives = sorted(archive_dir.glob("run_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

        errors = []
        for archive_path in archives[:10]:  # Check last 10 archives
            try:
                with zipfile.ZipFile(archive_path, 'r') as archive:
                    manifest = get_manifest(archive)
                    assert "run_id" in manifest
                    assert "routing_history" in manifest
            except Exception as e:
                errors.append(f"{archive_path.name}: {e}")

        if errors:
            pytest.fail(f"Invalid archives found:\n" + "\n".join(errors))

    def test_no_empty_archives(self, archive_dir):
        """Verify no archives are empty or corrupted."""
        if not archive_dir.exists():
            pytest.skip("Archive directory does not exist")

        archives = list(archive_dir.glob("run_*.zip"))

        for archive_path in archives:
            assert archive_path.stat().st_size > 100, f"Archive too small: {archive_path.name}"

            try:
                with zipfile.ZipFile(archive_path, 'r') as archive:
                    assert len(archive.namelist()) >= 2, f"Archive has too few files: {archive_path.name}"
            except zipfile.BadZipFile:
                pytest.fail(f"Corrupted archive: {archive_path.name}")

    def test_archives_have_unique_run_ids(self, archive_dir):
        """Verify each archive has a unique run_id."""
        if not archive_dir.exists():
            pytest.skip("Archive directory does not exist")

        archives = sorted(archive_dir.glob("run_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

        run_ids = set()
        for archive_path in archives[:20]:
            with zipfile.ZipFile(archive_path, 'r') as archive:
                manifest = get_manifest(archive)
                run_id = manifest["run_id"]

                assert run_id not in run_ids, f"Duplicate run_id: {run_id}"
                run_ids.add(run_id)
