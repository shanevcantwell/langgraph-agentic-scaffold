import json
import os
import hashlib
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.src.specialists.schemas._manifest import (
    ProjectManifest,
    BranchPointer,
    ContributionEntry,
    BranchStatus,
    AgentAffinity,
)

class ManifestManager:
    """
    Manages the lifecycle of the project manifest (The Heap).
    Enforces atomic writes, security invariants, and hash chaining.
    """

    def __init__(self, manifest_path: str):
        self.manifest_path = Path(manifest_path).resolve()
        self.project_root = self.manifest_path.parent
        self.manifest: Optional[ProjectManifest] = None

    def create_project(self, project_id: str, project_name: str, trunk_path: str) -> ProjectManifest:
        """Initialize a new project manifest."""
        self.manifest = ProjectManifest(
            project_id=project_id,
            project_name=project_name,
            trunk_document_path=trunk_path
        )
        self._save()
        return self.manifest

    def load(self) -> ProjectManifest:
        """Load the manifest from disk."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")
        
        with open(self.manifest_path, 'r') as f:
            data = json.load(f)
        
        self.manifest = ProjectManifest(**data)
        return self.manifest

    def _save(self):
        """
        Atomically save the manifest to disk.
        Writes to a temp file first, then uses os.replace() for atomic swap.
        """
        if not self.manifest:
            raise ValueError("No manifest to save")

        # Serialize to JSON
        data = self.manifest.model_dump(mode='json')
        json_str = json.dumps(data, indent=2)

        # Write to temp file in the same directory (ensures same filesystem for atomic move)
        # We use delete=False so we can close it before moving
        with tempfile.NamedTemporaryFile('w', dir=self.project_root, delete=False, suffix='.tmp') as tf:
            temp_path = Path(tf.name)
            try:
                tf.write(json_str)
                tf.flush()
                os.fsync(tf.fileno()) # Ensure write hits disk
            except Exception:
                # If write fails, close and delete temp file
                tf.close()
                if temp_path.exists():
                    os.unlink(temp_path)
                raise

        # Atomic swap
        try:
            os.replace(temp_path, self.manifest_path)
        except OSError:
            # If swap fails, clean up temp file
            if temp_path.exists():
                os.unlink(temp_path)
            raise

    def _validate_path(self, filepath: str) -> str:
        """
        Enforce path confinement.
        Filepath must be relative and stay within project root.
        """
        # 1. Check for absolute paths
        if os.path.isabs(filepath):
            raise ValueError(f"Path traversal attempt: Absolute path '{filepath}' not allowed.")

        # 2. Resolve path relative to project root
        full_path = (self.project_root / filepath).resolve()

        # 3. Check if resolved path is within project root
        # We use commonpath to check if project_root is a parent of full_path
        try:
            common = os.path.commonpath([self.project_root, full_path])
            if Path(common) != self.project_root:
                raise ValueError(f"Path traversal attempt: '{filepath}' resolves outside project root.")
        except ValueError:
             # commonpath raises ValueError if paths are on different drives (Windows)
             raise ValueError(f"Path traversal attempt: '{filepath}' resolves outside project root.")

        return filepath

    def add_branch(
        self,
        branch_id: str,
        title: str,
        filepath: str,
        context_snippet: str,
        affinity: AgentAffinity = AgentAffinity.DEFAULT,
        dependencies: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> BranchPointer:
        """Add a new branch pointer to the manifest."""
        if not self.manifest:
            self.load()

        if branch_id in self.manifest.branches:
            raise ValueError(f"Branch '{branch_id}' already exists.")

        # Security check
        safe_path = self._validate_path(filepath)

        branch = BranchPointer(
            id=branch_id,
            title=title,
            filepath=safe_path,
            context_snippet=context_snippet,
            affinity=affinity,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )

        self.manifest.branches[branch_id] = branch
        self.manifest.updated_at = datetime.now(timezone.utc)
        self._save()
        return branch

    def update_branch_status(self, branch_id: str, status: BranchStatus):
        """Update the status of a branch."""
        if not self.manifest:
            self.load()
        
        if branch_id not in self.manifest.branches:
            raise KeyError(f"Branch {branch_id} not found")

        self.manifest.branches[branch_id].status = status
        self.manifest.branches[branch_id].updated_at = datetime.now(timezone.utc)
        self._save()

    def update_context_snippet(self, branch_id: str, new_snippet: str):
        """Update the context snippet for a branch."""
        if not self.manifest:
            self.load()
        
        if branch_id not in self.manifest.branches:
            raise KeyError(f"Branch {branch_id} not found")

        self.manifest.branches[branch_id].context_snippet = new_snippet
        self.manifest.branches[branch_id].updated_at = datetime.now(timezone.utc)
        self._save()

    def log_contribution(
        self,
        branch_id: str,
        agent_id: str,
        agent_model: str,
        summary: str,
        content: str = ""
    ) -> ContributionEntry:
        """
        Log an agent's contribution with hash chaining.
        """
        if not self.manifest:
            self.load()

        # Calculate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Calculate previous hash
        previous_hash = None
        if self.manifest.contribution_log:
            last_entry = self.manifest.contribution_log[-1]
            # Formula: SHA256(previous_hash + content_hash)
            # Handle genesis block (previous_hash is None)
            prev_hash_str = str(last_entry.previous_hash or "")
            previous_hash = hashlib.sha256(
                (prev_hash_str + last_entry.content_hash).encode()
            ).hexdigest()

        entry = ContributionEntry(
            branch_id=branch_id,
            agent_id=agent_id,
            agent_model=agent_model,
            summary=summary,
            content_hash=content_hash,
            previous_hash=previous_hash
        )

        self.manifest.contribution_log.append(entry)
        self.manifest.updated_at = datetime.now(timezone.utc)
        self._save()
        return entry

    def verify_log_integrity(self) -> List[str]:
        """
        Verify the hash chain of the contribution log.
        Returns a list of violation messages (empty if valid).
        """
        if not self.manifest:
            self.load()

        violations = []
        log = self.manifest.contribution_log

        if not log:
            return violations

        # Check genesis
        if log[0].previous_hash is not None:
            violations.append("Genesis entry (index 0) has non-None previous_hash")

        # Check chain
        for i in range(1, len(log)):
            current = log[i]
            previous = log[i-1]

            expected_prev_hash = hashlib.sha256(
                (str(previous.previous_hash or "") + previous.content_hash).encode()
            ).hexdigest()

            if current.previous_hash != expected_prev_hash:
                violations.append(f"Chain broken at index {i}: expected {expected_prev_hash}, got {current.previous_hash}")

        return violations

    # =========================================================================
    # QUERY HELPERS
    # =========================================================================

    def get_branches_by_status(self, status: BranchStatus) -> List[BranchPointer]:
        """Return all branches with a specific status."""
        if not self.manifest:
            self.load()
        return [b for b in self.manifest.branches.values() if b.status == status]

    def get_branches_by_affinity(self, affinity: AgentAffinity) -> List[BranchPointer]:
        """Return all branches with a specific affinity tag."""
        if not self.manifest:
            self.load()
        
        return [b for b in self.manifest.branches.values() if b.affinity == affinity]

    def check_dependencies_satisfied(self, branch_id: str) -> bool:
        """
        Check if all dependencies of a branch are in a 'complete' or 'converged' state.
        """
        if not self.manifest:
            self.load()
        
        if branch_id not in self.manifest.branches:
            raise KeyError(f"Branch {branch_id} not found")

        branch = self.manifest.branches[branch_id]
        
        if not branch.dependencies:
            return True

        for dep_id in branch.dependencies:
            if dep_id not in self.manifest.branches:
                # Dependency missing implies not satisfied
                return False
            
            dep_status = self.manifest.branches[dep_id].status
            # Assuming 'complete' and 'converged' are the only satisfying states
            # The ADR might specify others, but this is a reasonable default
            if dep_status not in (BranchStatus.COMPLETE, BranchStatus.CONVERGED):
                return False
        
        return True
