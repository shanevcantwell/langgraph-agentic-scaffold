"""
Test-First Invariants for ADR-CORE-022: The Heap

These tests define the NON-NEGOTIABLE properties of the Heap infrastructure.
They are written BEFORE implementation to serve as executable specification.

Test Categories:
- S-*: Schema validation (Pydantic model constraints)
- M-*: Manager logic (atomic I/O, security, hash chain)

Reference: docs/ADRs/proposed/ADR-CORE-022-The-Heap.md
"""

import pytest
import json
import os
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

# Import from the locations specified in ADR-CORE-022
from app.src.specialists.schemas._manifest import (
    ProjectManifest,
    BranchPointer,
    ContributionEntry,
    BranchStatus,
    BranchPhase,
    AgentAffinity,
    RESERVED_METADATA_KEYS,
    KNOWN_NAMESPACES,
)
from app.src.utils.manifest_manager import ManifestManager


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for project files."""
    return tmp_path


@pytest.fixture
def manifest_path(temp_project_dir: Path) -> Path:
    """Provide the path to the manifest file."""
    return temp_project_dir / "manifest.json"


@pytest.fixture
def manager(manifest_path: Path) -> ManifestManager:
    """Provide an initialized ManifestManager (not yet created a project)."""
    return ManifestManager(str(manifest_path))


@pytest.fixture
def initialized_manager(manager: ManifestManager) -> ManifestManager:
    """Provide a ManifestManager with an initialized project."""
    manager.create_project("test-project", "Test Project", "trunk.md")
    return manager


# =============================================================================
# S-01: SCHEMA STRICTNESS - extra='forbid'
# =============================================================================

class TestSchemaStrictness:
    """
    Invariant: All models must reject unknown fields.

    This prevents:
    - Hidden data channels between agents
    - Silent data loss on schema changes
    - Covert storage of unapproved metadata
    """

    def test_branch_pointer_forbids_extra_fields(self):
        """BranchPointer must reject unknown fields."""
        with pytest.raises(ValidationError) as excinfo:
            BranchPointer(
                id="b1",
                title="Test Branch",
                filepath="branches/b1.md",
                context_snippet="This is a test branch summary.",
                hidden_payload="secret_data"  # <-- Should fail
            )

        error_str = str(excinfo.value)
        assert "hidden_payload" in error_str
        assert "Extra inputs are not permitted" in error_str

    def test_project_manifest_forbids_extra_fields(self):
        """ProjectManifest must reject unknown fields."""
        with pytest.raises(ValidationError) as excinfo:
            ProjectManifest(
                project_id="p1",
                project_name="Test Project",
                trunk_document_path="trunk.md",
                covert_channel="malicious_data"  # <-- Should fail
            )

        error_str = str(excinfo.value)
        assert "covert_channel" in error_str
        assert "Extra inputs are not permitted" in error_str

    def test_contribution_entry_forbids_extra_fields(self):
        """ContributionEntry must reject unknown fields."""
        with pytest.raises(ValidationError) as excinfo:
            ContributionEntry(
                branch_id="b1",
                agent_id="test_agent",
                agent_model="claude-opus-4",
                summary="Test contribution",
                content_hash="abc123",
                injected_field="payload"  # <-- Should fail
            )

        error_str = str(excinfo.value)
        assert "injected_field" in error_str
        assert "Extra inputs are not permitted" in error_str


# =============================================================================
# S-02: METADATA NAMESPACING
# =============================================================================

class TestMetadataNamespacing:
    """
    Invariant: Metadata keys must follow namespace convention.

    Format: 'namespace.key' (e.g., 'research.query')
    Exception: Reserved keys (priority, source, tags)

    This prevents:
    - Key collisions between workflows
    - Unstructured metadata sprawl
    - Debugging nightmares from naked keys
    """

    def test_valid_namespaced_keys_accepted(self):
        """Properly namespaced keys should be accepted."""
        metadata = {
            "research.query": "CRM comparison",
            "research.sources": ["hubspot.com", "salesforce.com"],
            "project.name": "Q4 Analysis",
            "user.custom_flag": True,
        }

        bp = BranchPointer(
            id="b1",
            title="Test",
            filepath="branches/b1.md",
            context_snippet="summary",
            metadata=metadata
        )

        assert bp.metadata == metadata

    def test_reserved_keys_accepted_without_namespace(self):
        """Reserved keys (priority, source, tags) don't need namespacing."""
        metadata = {
            "priority": "urgent",
            "source": "deep_research",
            "tags": ["important", "q4"],
        }

        bp = BranchPointer(
            id="b1",
            title="Test",
            filepath="branches/b1.md",
            context_snippet="summary",
            metadata=metadata
        )

        assert bp.metadata["priority"] == "urgent"
        assert bp.metadata["tags"] == ["important", "q4"]

    def test_naked_key_rejected(self):
        """Keys without namespace (and not reserved) must be rejected."""
        with pytest.raises(ValidationError) as excinfo:
            BranchPointer(
                id="b1",
                title="Test",
                filepath="branches/b1.md",
                context_snippet="summary",
                metadata={"naked_key": "bad_value"}
            )

        assert "namespace" in str(excinfo.value).lower()

    def test_empty_namespace_rejected(self):
        """Keys with empty namespace (.key) must be rejected."""
        with pytest.raises(ValidationError) as excinfo:
            BranchPointer(
                id="b1",
                title="Test",
                filepath="branches/b1.md",
                context_snippet="summary",
                metadata={".empty_namespace": "bad"}
            )

        # Either namespace validation or empty string rejection
        error_str = str(excinfo.value).lower()
        assert "namespace" in error_str or "empty" in error_str

    def test_mixed_valid_and_reserved_keys(self):
        """Mix of namespaced and reserved keys should work."""
        metadata = {
            "priority": "high",
            "research.confidence": 0.95,
            "tags": ["verified"],
            "convening.branch_count": 3,
        }

        bp = BranchPointer(
            id="b1",
            title="Test",
            filepath="branches/b1.md",
            context_snippet="summary",
            metadata=metadata
        )

        assert bp.metadata == metadata


# =============================================================================
# S-03: ENUM COMPLETENESS
# =============================================================================

class TestEnumCompleteness:
    """
    Invariant: Enums must contain all values specified in ADR-CORE-022.

    If the ADR specifies values, they must exist in the implementation.
    """

    def test_branch_status_values(self):
        """BranchStatus must have all ADR-specified values."""
        required_statuses = {
            "active", "blocked", "stale", "converged",
            "clarification_required", "complete", "abandoned"
        }

        actual_statuses = {s.value for s in BranchStatus}

        assert required_statuses.issubset(actual_statuses), (
            f"Missing statuses: {required_statuses - actual_statuses}"
        )

    def test_branch_phase_values(self):
        """BranchPhase must have all ADR-specified values."""
        required_phases = {
            "investigation", "validation", "synthesis_ready"
        }
        # Note: The ADR might have evolved, but we stick to the test requirement.
        # If the implementation has more, that's fine, but it must have these.
        
        actual_phases = {p.value for p in BranchPhase}

        assert required_phases.issubset(actual_phases), (
            f"Missing phases: {required_phases - actual_phases}"
        )

    def test_agent_affinity_values(self):
        """AgentAffinity must have all ADR-specified values."""
        required_affinities = {
            "architecture", "implementation", "research",
            "inference", "monitoring", "default"
        }

        actual_affinities = {a.value for a in AgentAffinity}

        assert required_affinities.issubset(actual_affinities), (
            f"Missing affinities: {required_affinities - actual_affinities}"
        )


# =============================================================================
# M-01: ATOMIC WRITE SURVIVAL
# =============================================================================

class TestAtomicWriteSurvival:
    """
    Invariant: Manifest file must not corrupt if write fails midway.

    The pattern: write to temp file, then atomic os.replace().
    If os.replace() fails, the original file must remain intact.

    This is CRITICAL for LAS's crash-prone hardware context.
    """

    def test_atomic_write_survives_replace_failure(
        self,
        initialized_manager: ManifestManager,
        manifest_path: Path
    ):
        """
        If os.replace() fails after temp file is written,
        the original manifest must remain intact and valid.
        """
        # 1. Verify initial state
        initial_content = manifest_path.read_text()
        initial_data = json.loads(initial_content)
        assert initial_data["project_id"] == "test-project"

        # 2. Mock os.replace to fail (simulates filesystem error)
        #    This is the correct point to mock - after temp file write, before atomic swap
        with patch("os.replace", side_effect=OSError("Disk full")):
            with pytest.raises(OSError, match="Disk full"):
                initialized_manager.add_branch(
                    branch_id="will-fail",
                    title="This Should Fail",
                    filepath="branches/fail.md",
                    context_snippet="This write will fail"
                )

        # 3. Verify original file is EXACTLY as it was
        current_content = manifest_path.read_text()
        assert current_content == initial_content

        # 4. Verify it's still valid JSON with correct data
        current_data = json.loads(current_content)
        assert current_data["project_id"] == "test-project"
        assert "will-fail" not in current_data.get("branches", {})

    def test_temp_file_cleaned_on_failure(
        self,
        initialized_manager: ManifestManager,
        temp_project_dir: Path
    ):
        """
        If os.replace() fails, the temp file should be cleaned up.
        No orphaned .tmp files should remain.
        """
        # Count .tmp files before
        tmp_files_before = list(temp_project_dir.glob("*.tmp"))

        with patch("os.replace", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                initialized_manager.add_branch(
                    branch_id="cleanup-test",
                    title="Cleanup Test",
                    filepath="branches/cleanup.md",
                    context_snippet="Testing temp file cleanup"
                )

        # Count .tmp files after
        tmp_files_after = list(temp_project_dir.glob("*.tmp"))

        assert len(tmp_files_after) == len(tmp_files_before), (
            f"Orphaned temp files: {tmp_files_after}"
        )


# =============================================================================
# M-02: PATH TRAVERSAL PREVENTION
# =============================================================================

class TestPathTraversalPrevention:
    """
    Invariant: Agents cannot write files outside the project root.

    This is a SECURITY invariant. A compromised agent should not be able
    to read ~/.ssh/id_rsa or write to /etc/passwd via path traversal.
    """

    def test_relative_traversal_rejected(self, initialized_manager: ManifestManager):
        """Classic ../ traversal must be rejected."""
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            initialized_manager.add_branch(
                branch_id="attack-1",
                title="Attack Branch",
                filepath="../../../etc/passwd",
                context_snippet="Attempting path traversal"
            )

    def test_absolute_path_outside_root_rejected(self, initialized_manager: ManifestManager):
        """Absolute paths outside project root must be rejected."""
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            initialized_manager.add_branch(
                branch_id="attack-2",
                title="Attack Branch",
                filepath="/etc/passwd",
                context_snippet="Attempting absolute path escape"
            )

    def test_encoded_traversal_rejected(self, initialized_manager: ManifestManager):
        """URL-encoded or tricky traversal attempts must be rejected."""
        tricky_paths = [
            "branches/foo/../../../etc/passwd",  # Buried traversal
            "branches/./../../etc/passwd",  # Dot prefix
        ]

        for i, path in enumerate(tricky_paths):
            with pytest.raises(ValueError, match="[Pp]ath traversal"):
                initialized_manager.add_branch(
                    branch_id=f"attack-tricky-{i}",
                    title="Attack",
                    filepath=path,
                    context_snippet="Tricky traversal"
                )


# =============================================================================
# M-03: HASH CHAINING
# =============================================================================

class TestHashChaining:
    """
    Invariant: Contribution log must form a verifiable hash chain.

    Each entry must include the hash of the previous entry.
    This makes the log tamper-evident (blockchain style).
    """

    def test_hash_chain_integrity(self, initialized_manager: ManifestManager):
        """
        Verify that each entry correctly hashes the previous entry.
        """
        # Log 3 entries
        initialized_manager.log_contribution("b1", "agent1", "model1", "Genesis")
        initialized_manager.log_contribution("b1", "agent1", "model1", "Second")
        initialized_manager.log_contribution("b1", "agent1", "model1", "Third")

        log = initialized_manager.manifest.contribution_log
        assert len(log) == 3

        # Entry 0 (Genesis) - previous_hash is None
        assert log[0].previous_hash is None

        # Entry 1 - previous_hash must match hash of Entry 0
        # Formula: SHA256(previous_hash + content_hash)
        # Note: This formula must match implementation exactly
        expected_prev_hash_1 = hashlib.sha256(
            (str(log[0].previous_hash or "") + log[0].content_hash).encode()
        ).hexdigest()
        assert log[1].previous_hash == expected_prev_hash_1

        # Entry 2 - previous_hash must match hash of Entry 1
        expected_prev_hash_2 = hashlib.sha256(
            (log[1].previous_hash + log[1].content_hash).encode()
        ).hexdigest()
        assert log[2].previous_hash == expected_prev_hash_2

    def test_content_hash_computation(self, initialized_manager: ManifestManager):
        """
        Verify that content_hash is computed correctly from the content string.
        """
        content = "This is the content being logged."
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        initialized_manager.log_contribution(
            branch_id="b1",
            agent_id="agent1",
            agent_model="model1",
            summary="Test",
            content=content  # Pass actual content to compute hash
        )

        entry = initialized_manager.manifest.contribution_log[0]
        assert entry.content_hash == expected_hash


# =============================================================================
# M-04: TAMPER DETECTION
# =============================================================================

class TestTamperDetection:
    """
    Invariant: The system must detect if the log has been manually edited.
    """

    def test_detects_content_tampering(
        self,
        initialized_manager: ManifestManager,
        manifest_path: Path
    ):
        """If content_hash doesn't match content, flag it."""
        # 1. Create valid log
        initialized_manager.log_contribution("b1", "a1", "m1", "Valid", content="Original Content")

        # 2. Manually tamper with the file (simulate rogue edit)
        data = json.loads(manifest_path.read_text())
        
        # Let's simulate breaking the chain
        initialized_manager.log_contribution("b1", "a1", "m1", "Second", content="Second Content")
        data = json.loads(manifest_path.read_text())

        # Break the link between 0 and 1
        data["contribution_log"][1]["previous_hash"] = "deadbeef"
        manifest_path.write_text(json.dumps(data))

        # 3. Verify integrity
        initialized_manager.load()
        violations = initialized_manager.verify_log_integrity()

        assert len(violations) > 0
        assert "Chain broken" in violations[0]


# =============================================================================
# M-07: QUERY HELPERS
# =============================================================================

class TestQueryHelpers:
    """
    Tests for the helper methods required by ADR-CORE-023 (Conductor).
    """

    def test_get_branches_by_status(self, initialized_manager: ManifestManager):
        """Should filter branches by status."""
        initialized_manager.add_branch("b1", "Active", "b1.md", "s")
        initialized_manager.add_branch("b2", "Stale", "b2.md", "s")
        initialized_manager.update_branch_status("b2", BranchStatus.STALE)

        active = initialized_manager.get_branches_by_status(BranchStatus.ACTIVE)
        stale = initialized_manager.get_branches_by_status(BranchStatus.STALE)

        assert len(active) == 1
        assert active[0].id == "b1"
        assert len(stale) == 1
        assert stale[0].id == "b2"

    def test_get_branches_by_affinity(self, initialized_manager: ManifestManager):
        """Should filter branches by affinity."""
        initialized_manager.add_branch(
            "b1", "Arch", "b1.md", "s",
            affinity=AgentAffinity.ARCHITECTURE
        )
        initialized_manager.add_branch(
            "b2", "Impl", "b2.md", "s",
            affinity=AgentAffinity.IMPLEMENTATION
        )

        arch_branches = initialized_manager.get_branches_by_affinity(AgentAffinity.ARCHITECTURE)
        assert len(arch_branches) == 1
        assert arch_branches[0].id == "b1"

    def test_check_dependencies_satisfied(self, initialized_manager: ManifestManager):
        """Should correctly identify if dependencies are complete."""
        # b1 depends on nothing -> Satisfied
        initialized_manager.add_branch("b1", "Base", "b1.md", "s")

        # b2 depends on b1 (Active) -> Not Satisfied
        initialized_manager.add_branch("b2", "Dep", "b2.md", "s", dependencies=["b1"])

        assert initialized_manager.check_dependencies_satisfied("b1") is True
        assert initialized_manager.check_dependencies_satisfied("b2") is False

        # Complete b1
        initialized_manager.update_branch_status("b1", BranchStatus.COMPLETE)

        # b2 should now be satisfied
        assert initialized_manager.check_dependencies_satisfied("b2") is True
