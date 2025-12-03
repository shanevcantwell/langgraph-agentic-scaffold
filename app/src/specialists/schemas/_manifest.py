from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationInfo

# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class BranchStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    STALE = "stale"
    CONVERGED = "converged"
    CLARIFICATION_REQUIRED = "clarification_required"
    COMPLETE = "complete"
    ABANDONED = "abandoned"

class BranchPhase(str, Enum):
    INVESTIGATION = "investigation"
    VALIDATION = "validation"
    SYNTHESIS_READY = "synthesis_ready"

class AgentAffinity(str, Enum):
    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    RESEARCH = "research"
    INFERENCE = "inference"
    MONITORING = "monitoring"
    DEFAULT = "default"

RESERVED_METADATA_KEYS = {"priority", "source", "tags"}
KNOWN_NAMESPACES = {"research", "project", "user", "convening"}

# =============================================================================
# MODELS
# =============================================================================

class ContributionEntry(BaseModel):
    """
    Immutable record of an agent's contribution to a branch.
    Forms a hash chain for tamper-evidence.
    """
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    branch_id: str
    agent_id: str
    agent_model: str
    summary: str
    content_hash: str
    previous_hash: Optional[str] = None


class BranchPointer(BaseModel):
    """
    Lightweight pointer to a branch file.
    Stored in the manifest to allow rapid scanning without opening branch files.
    """
    model_config = ConfigDict(extra='forbid')

    id: str
    title: str
    filepath: str
    status: BranchStatus = BranchStatus.ACTIVE
    phase: BranchPhase = BranchPhase.INVESTIGATION
    affinity: AgentAffinity = AgentAffinity.DEFAULT
    context_snippet: str
    dependencies: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('metadata')
    @classmethod
    def validate_metadata_keys(cls, v: Dict[str, Any], info: ValidationInfo) -> Dict[str, Any]:
        """
        Enforce namespacing for metadata keys.
        Keys must be either in RESERVED_METADATA_KEYS or follow 'namespace.key' format.
        """
        for key in v.keys():
            if key in RESERVED_METADATA_KEYS:
                continue
            
            if '.' not in key:
                raise ValueError(f"Metadata key '{key}' must be namespaced (e.g., 'research.query') or reserved.")
            
            namespace, _ = key.split('.', 1)
            if not namespace:
                raise ValueError(f"Metadata key '{key}' has empty namespace.")
                
        return v


class ProjectManifest(BaseModel):
    """
    The root state object for 'The Heap'.
    Persisted as manifest.json in the project root.
    """
    model_config = ConfigDict(extra='forbid')

    project_id: str
    project_name: str
    trunk_document_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    branches: Dict[str, BranchPointer] = Field(default_factory=dict)
    contribution_log: List[ContributionEntry] = Field(default_factory=list)

# =============================================================================
# LEGACY / ARCHIVER MODELS
# =============================================================================

class ArtifactManifest(BaseModel):
    """Metadata for a single artifact in the package."""
    filename: str
    original_key: str
    content_type: str = "text/plain"
    size_bytes: int

class AtomicManifest(BaseModel):
    """
    The formal schema for the Atomic Archival Package manifest.
    This file (manifest.json) is included in the root of every .zip archive.
    """
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = Field(..., description="Unique identifier for this execution run.")
    routing_history: List[str] = Field(default_factory=list)
    artifacts: List[ArtifactManifest] = Field(default_factory=list)
    final_response_generated: bool
    termination_reason: str = "success"
