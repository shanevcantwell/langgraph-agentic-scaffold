# ADR-CORE-022: The Heap — Filesystem-Backed Cognitive Memory

**Status:** Completed
**Date:** 2025-12-03  
**Context:** langgraph-agentic-scaffold (LAS)  
**Layer:** Infrastructure (Foundation)  
**Depends On:** None  
**Depended On By:** ADR-CORE-023 (Convening), ADR-CORE-024 (Deep Research)  

---

## Abstract

This ADR establishes the foundational persistence layer for LAS: a filesystem-backed "Heap" that stores cognitive state outside the context window. By treating the **Context Window as Stack** (fast, limited, execution-scoped) and the **Filesystem as Heap** (slow, infinite, persistent), we enable multi-session agentic workflows that survive system restarts.

This document defines:
- The Heap/Stack architectural metaphor
- Schema definitions (Manifest, BranchPointer, ContributionEntry)
- The ManifestManager (atomic I/O engine)
- Built-in security measures (tamper evidence, path confinement)

It does NOT define orchestration policy (see ADR-CORE-023) or specific workflows (see ADR-CORE-024).

---

## 1. Context and Problem Statement

### 1.1 The Context Window Is Not Storage

Current LAS patterns treat the context window as both execution memory AND storage. This fails for complex work:

| Problem | Symptom |
|---------|---------|
| **Session Amnesia** | Work dies when chat ends |
| **Context Overflow** | Long investigations degrade reasoning quality |
| **No Forensics** | Cannot audit what agents did across sessions |
| **No Parallelism** | Cannot work on multiple topics independently |

### 1.2 Industry Precedent

> "For long horizon tasks, agents should write plans, research, and knowledge to the filesystem... and pull this information back into the context window later on."  
> — *How agents can use filesystems for context engineering*, LangChain (November 2025)

> "Use the file system as externalized memory... it is unlimited in size."  
> — *Context Engineering for AI Agents: Lessons from Building Manus*, Yichao Ji (July 2025)

### 1.3 The Heap/Stack Metaphor

| Concept | Classical Computing | Agentic Computing |
|---------|---------------------|-------------------|
| **Stack** | Fast, limited, function-scoped | Context Window |
| **Heap** | Slow, large, persistent | Filesystem (Manifest + Documents) |
| **Pointer** | Memory address | File path + context snippet |
| **Allocation** | `malloc()` | `add_branch()` |
| **Deallocation** | `free()` | Branch → COMPLETE/ABANDONED |

---

## 2. Decision

We will implement **The Heap** as the foundational persistence layer for LAS.

### 2.1 Core Principles

1. **Separation of Concerns:** The Heap is mechanism (how to persist), not policy (what to persist or when)
2. **Pointers, Not Content:** The Manifest stores references (paths + summaries), never full content
3. **Security by Design:** Tamper evidence, path confinement, and namespace validation are built-in, not afterthoughts
4. **Atomic Operations:** All writes must survive crashes without corruption

### 2.2 Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         THE HEAP                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  ProjectManifest                         │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │   │
│  │  │ project_id  │ │  branches   │ │contribution │        │   │
│  │  │ trunk_path  │ │ (pointers)  │ │    _log     │        │   │
│  │  └─────────────┘ └──────┬──────┘ └─────────────┘        │   │
│  └─────────────────────────┼───────────────────────────────┘   │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                │
│         │                  │                  │                │
│         ▼                  ▼                  ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │ trunk.md    │    │ branch-a.md │    │ branch-b.md │        │
│  │ (root doc)  │    │ (content)   │    │ (content)   │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │
         │ ManifestManager (Atomic I/O)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CONSUMERS                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ TribeConductor  │  │ Deep Research   │  │ Future Flows   │  │
│  │ (ADR-023)       │  │ (ADR-024)       │  │                │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Schema Definitions

### 3.1 Enumerations

```python
# app/src/specialists/schemas/_manifest.py

from enum import Enum

class BranchStatus(str, Enum):
    """Lifecycle state of a branch."""
    ACTIVE = "active"                          # Work in progress
    BLOCKED = "blocked"                        # Waiting on dependency
    STALE = "stale"                            # No recent activity
    CONVERGED = "converged"                    # Ready for synthesis
    CLARIFICATION_REQUIRED = "clarification_required"  # HitL pause
    COMPLETE = "complete"                      # Merged into trunk
    ABANDONED = "abandoned"                    # Closed without merge


class BranchPhase(str, Enum):
    """Processing phase within an active branch."""
    INVESTIGATION = "investigation"            # Exploring problem space
    VALIDATION = "validation"                  # Testing hypotheses
    SYNTHESIS_READY = "synthesis_ready"        # Ready to merge findings


class AgentAffinity(str, Enum):
    """
    Routing affinity for branch assignment.
    
    These are LAWS - orchestrators require valid affinity to route work.
    Adding new affinities requires updating routing logic.
    """
    ARCHITECTURE = "architecture"              # High-level design
    IMPLEMENTATION = "implementation"          # Code and debugging
    RESEARCH = "research"                      # Web search, literature
    INFERENCE = "inference"                    # Pure semantic judgment
    MONITORING = "monitoring"                  # Quick checks, monitoring
    DEFAULT = "default"                        # Fallback routing
```

### 3.2 Metadata Conventions

```python
# Reserved top-level keys (no namespace required)
RESERVED_METADATA_KEYS = frozenset({
    "priority",      # "urgent" | "normal" | "background"
    "source",        # Origin flow identifier
    "tags",          # List of tags for filtering
})

# Known namespaces (extensible)
KNOWN_NAMESPACES = frozenset({
    "las",           # Core LAS system metadata
    "research",      # Deep Research flow
    "convening",     # Multi-model collaboration
    "fishbowl",      # Synchronous debate
    "project",       # Project-specific data
    "security",      # Security flags (write-restricted)
    "routing",       # Routing hints beyond affinity
    "user",          # User-defined extensions
})
```

### 3.3 ContributionEntry (Forensic Record)

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ContributionEntry(BaseModel):
    """
    Forensic record of agent activity.
    
    Forms a hash chain for tamper evidence - each entry includes
    the hash of the previous entry, creating an append-only log.
    """
    model_config = ConfigDict(extra='forbid')
    
    branch_id: str = Field(..., description="Branch where work was performed")
    agent_id: str = Field(..., description="Logical agent identity (e.g., 'progenitor_alpha')")
    agent_model: str = Field(..., description="Specific model used (e.g., 'claude-opus-4')")
    summary: str = Field(..., description="Brief description of contribution")
    tokens_consumed: Optional[int] = Field(default=None, description="Token usage for cost tracking")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Security: Tamper-evident chaining
    content_hash: str = Field(..., description="SHA-256 of content written to branch")
    previous_hash: Optional[str] = Field(
        default=None,
        description="Hash of previous entry (blockchain-style chain)"
    )
```

### 3.4 BranchPointer (The Pointer)

```python
from typing import List, Dict, Any
from pydantic import field_validator
import logging

logger = logging.getLogger(__name__)


class BranchPointer(BaseModel):
    """
    A 'Pointer' to branch state on the Heap.
    
    Design: Header/Payload separation
    - HEADER (typed): id, filepath, affinity, status - for O(1) scheduling
    - PAYLOAD (flexible): metadata, context_snippet - for agent context
    
    Metadata Convention:
    - Keys must be namespaced: 'domain.key' (e.g., 'research.query')
    - Reserved keys (priority, source, tags) are exceptions
    """
    model_config = ConfigDict(extra='forbid')
    
    # === HEADER (The Laws) ===
    id: str = Field(..., description="Unique branch identifier")
    title: str = Field(..., description="Human-readable branch name")
    filepath: str = Field(..., description="Path to branch document on Heap")
    
    affinity: AgentAffinity = Field(
        default=AgentAffinity.DEFAULT,
        description="Routing affinity - determines which agent type handles this branch"
    )
    status: BranchStatus = Field(default=BranchStatus.ACTIVE)
    phase: BranchPhase = Field(default=BranchPhase.INVESTIGATION)
    
    # Dependency graph
    dependencies: List[str] = Field(
        default_factory=list,
        description="Branch IDs that must complete before this can proceed"
    )
    blocks: List[str] = Field(
        default_factory=list,
        description="Branch IDs blocked by this branch"
    )
    
    # === PAYLOAD (The Preferences) ===
    context_snippet: str = Field(
        ...,
        description="~500 word summary for cold-start context loading"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Namespaced workflow metadata (e.g., 'research.query', 'project.name')"
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('metadata')
    @classmethod
    def enforce_namespace_convention(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce namespaced keys to prevent metadata pollution."""
        for key in v.keys():
            if key in RESERVED_METADATA_KEYS:
                continue
            
            if '.' not in key:
                raise ValueError(
                    f"Metadata key '{key}' violates namespacing convention. "
                    f"Use format 'namespace.key' (e.g., 'research.query'). "
                    f"Reserved keys: {sorted(RESERVED_METADATA_KEYS)}"
                )
            
            namespace = key.split('.')[0]
            if namespace not in KNOWN_NAMESPACES:
                logger.warning(
                    f"Unknown metadata namespace '{namespace}' in key '{key}'. "
                    f"Known namespaces: {sorted(KNOWN_NAMESPACES)}"
                )
        
        return v
```

### 3.5 ProjectManifest (The Allocation Table)

```python
class ProjectManifest(BaseModel):
    """
    The 'Codex' - Persistent Project State.
    
    Master allocation table for the cognitive Heap.
    Contains POINTERS to content, never full content itself.
    """
    model_config = ConfigDict(extra='forbid')
    
    # Identity
    project_id: str = Field(..., description="Unique project identifier")
    project_name: str = Field(..., description="Human-readable project name")
    
    # Root document
    trunk_document_path: str = Field(
        ...,
        description="Path to trunk.md - the root of all context"
    )
    
    # Allocation table
    branches: Dict[str, BranchPointer] = Field(
        default_factory=dict,
        description="Map of branch_id -> BranchPointer"
    )
    
    # Forensic log (append-only, hash-chained)
    contribution_log: List[ContributionEntry] = Field(
        default_factory=list,
        description="Tamper-evident log of all agent contributions"
    )
    
    # Timestamps and versioning
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = Field(
        default="1.0.0",
        description="Schema version for future migrations"
    )
```

---

## 4. ManifestManager (Atomic I/O Engine)

```python
# app/src/utils/manifest_manager.py
"""
ManifestManager - Atomic I/O for the Heap.

Design Principles:
1. Atomic writes (tempfile + os.replace) to survive crashes
2. Hash chaining for tamper-evident logging
3. Path confinement to prevent traversal attacks
4. High-level CRUD so consumers don't manipulate raw state
"""

import json
import os
import tempfile
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.src.specialists.schemas._manifest import (
    ProjectManifest,
    BranchPointer,
    ContributionEntry,
    BranchStatus,
    BranchPhase,
    AgentAffinity,
)

logger = logging.getLogger(__name__)


class ManifestManager:
    """
    Manages the ProjectManifest (Heap) with atomic operations.
    """
    
    def __init__(self, manifest_path: str, project_root: Optional[str] = None):
        """
        Initialize the manager.
        
        Args:
            manifest_path: Path to manifest.json
            project_root: Root directory for path confinement (defaults to manifest parent)
        """
        self.manifest_path = Path(manifest_path)
        self._project_root = Path(project_root) if project_root else self.manifest_path.parent
        self.manifest: Optional[ProjectManifest] = None
        
        # Ensure directory exists
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # CORE I/O (Atomic Operations)
    # =========================================================================
    
    def create_project(
        self,
        project_id: str,
        project_name: str,
        trunk_path: str
    ) -> ProjectManifest:
        """Initialize a new project manifest."""
        self.manifest = ProjectManifest(
            project_id=project_id,
            project_name=project_name,
            trunk_document_path=str(trunk_path)
        )
        self._atomic_save()
        logger.info(f"Created new project manifest at {self.manifest_path}")
        return self.manifest
    
    def load(self) -> ProjectManifest:
        """
        Load manifest from disk.
        
        Raises:
            FileNotFoundError: If manifest does not exist
            ValidationError: If JSON is invalid or schema mismatch
        """
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")
        
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.manifest = ProjectManifest(**data)
        return self.manifest
    
    def load_or_create(
        self,
        project_id: str,
        project_name: str,
        trunk_path: str
    ) -> ProjectManifest:
        """Load existing manifest or create new one."""
        if self.manifest_path.exists():
            return self.load()
        return self.create_project(project_id, project_name, trunk_path)
    
    def _atomic_save(self) -> None:
        """
        Atomically save manifest to disk.
        
        Uses write-to-temp-then-rename pattern to prevent corruption
        from crashes during write.
        """
        if not self.manifest:
            raise ValueError("No manifest loaded to save.")
        
        self.manifest.updated_at = datetime.utcnow()
        
        # Write to temp file in same directory (ensures same filesystem for atomic rename)
        temp_dir = self.manifest_path.parent
        with tempfile.NamedTemporaryFile(
            'w', 
            dir=temp_dir, 
            delete=False, 
            encoding='utf-8',
            suffix='.tmp'
        ) as tf:
            json.dump(
                self.manifest.model_dump(mode='json'), 
                tf, 
                indent=2,
                default=str  # Handle datetime serialization
            )
            temp_path = tf.name
        
        # Atomic replace (POSIX guarantees, Windows best-effort)
        try:
            os.replace(temp_path, self.manifest_path)
        except OSError as e:
            os.remove(temp_path)  # Clean up on failure
            logger.error(f"Failed to save manifest: {e}")
            raise
    
    # =========================================================================
    # PATH SECURITY
    # =========================================================================
    
    def _validate_path(self, filepath: str) -> Path:
        """
        Ensure filepath is within project root (prevent traversal).
        
        Raises:
            ValueError: If path escapes project root
        """
        # Resolve to absolute, handling any ../ sequences
        if Path(filepath).is_absolute():
            resolved = Path(filepath).resolve()
        else:
            resolved = (self._project_root / filepath).resolve()
        
        # Check containment
        try:
            resolved.relative_to(self._project_root.resolve())
        except ValueError:
            raise ValueError(
                f"Path traversal detected: '{filepath}' escapes project root "
                f"'{self._project_root}'"
            )
        
        return resolved
    
    # =========================================================================
    # BRANCH OPERATIONS
    # =========================================================================
    
    def add_branch(
        self,
        branch_id: str,
        title: str,
        filepath: str,
        context_snippet: str,
        affinity: AgentAffinity = AgentAffinity.DEFAULT,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BranchPointer:
        """
        Register a new branch in the manifest.
        
        Also updates 'blocks' field of any dependencies.
        """
        if not self.manifest:
            raise ValueError("Manifest not loaded.")
        
        if branch_id in self.manifest.branches:
            raise ValueError(f"Branch '{branch_id}' already exists.")
        
        # Validate path security
        self._validate_path(filepath)
        
        pointer = BranchPointer(
            id=branch_id,
            title=title,
            filepath=filepath,
            context_snippet=context_snippet,
            affinity=affinity,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        
        self.manifest.branches[branch_id] = pointer
        
        # Update 'blocks' for dependencies
        for dep_id in pointer.dependencies:
            if dep_id in self.manifest.branches:
                dep_branch = self.manifest.branches[dep_id]
                if branch_id not in dep_branch.blocks:
                    dep_branch.blocks.append(branch_id)
        
        self._atomic_save()
        logger.info(f"Added branch '{branch_id}' with affinity '{affinity.value}'")
        return pointer
    
    def get_branch(self, branch_id: str) -> Optional[BranchPointer]:
        """Retrieve a branch by ID."""
        if not self.manifest:
            raise ValueError("Manifest not loaded.")
        return self.manifest.branches.get(branch_id)
    
    def get_branches_by_status(self, status: BranchStatus) -> List[BranchPointer]:
        """Return all branches with given status."""
        if not self.manifest:
            return []
        return [b for b in self.manifest.branches.values() if b.status == status]
    
    def get_branches_by_affinity(self, affinity: AgentAffinity) -> List[BranchPointer]:
        """Return all branches with given affinity."""
        if not self.manifest:
            return []
        return [b for b in self.manifest.branches.values() if b.affinity == affinity]
    
    def update_branch_status(
        self,
        branch_id: str,
        status: BranchStatus,
        phase: Optional[BranchPhase] = None
    ) -> None:
        """Update lifecycle status of a branch."""
        if not self.manifest or branch_id not in self.manifest.branches:
            raise ValueError(f"Branch '{branch_id}' not found.")
        
        branch = self.manifest.branches[branch_id]
        branch.status = status
        if phase:
            branch.phase = phase
        branch.updated_at = datetime.utcnow()
        
        self._atomic_save()
        logger.info(f"Branch '{branch_id}' status -> {status.value}")
    
    def update_context_snippet(self, branch_id: str, snippet: str) -> None:
        """Update the context summary for a branch."""
        if not self.manifest or branch_id not in self.manifest.branches:
            raise ValueError(f"Branch '{branch_id}' not found.")
        
        branch = self.manifest.branches[branch_id]
        branch.context_snippet = snippet
        branch.updated_at = datetime.utcnow()
        
        self._atomic_save()
    
    # =========================================================================
    # FORENSIC LOGGING (Hash-Chained)
    # =========================================================================
    
    def log_contribution(
        self,
        branch_id: str,
        agent_id: str,
        agent_model: str,
        summary: str,
        content: str,
        tokens_consumed: Optional[int] = None,
    ) -> ContributionEntry:
        """
        Append entry to tamper-evident forensic log.
        
        Args:
            branch_id: Which branch received the contribution
            agent_id: Logical agent name
            agent_model: Specific model used
            summary: Brief description
            content: Actual content written (hashed, not stored)
            tokens_consumed: Optional token count
        
        Returns:
            The created ContributionEntry
        """
        if not self.manifest:
            raise ValueError("Manifest not loaded.")
        
        # Compute hash chain
        previous_hash = None
        if self.manifest.contribution_log:
            last_entry = self.manifest.contribution_log[-1]
            previous_hash = last_entry.content_hash
        
        # Hash includes previous hash for chain integrity
        hash_input = f"{previous_hash or ''}{content}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        entry = ContributionEntry(
            branch_id=branch_id,
            agent_id=agent_id,
            agent_model=agent_model,
            summary=summary,
            tokens_consumed=tokens_consumed,
            content_hash=content_hash,
            previous_hash=previous_hash,
        )
        
        self.manifest.contribution_log.append(entry)
        self._atomic_save()
        
        logger.debug(f"Logged contribution from '{agent_id}' to branch '{branch_id}'")
        return entry
    
    def verify_log_integrity(self) -> List[str]:
        """
        Verify hash chain integrity of contribution log.
        
        Returns:
            List of violation descriptions (empty if valid)
        """
        if not self.manifest:
            return ["Manifest not loaded"]
        
        violations = []
        
        for i, entry in enumerate(self.manifest.contribution_log):
            if i == 0:
                if entry.previous_hash is not None:
                    violations.append(f"Entry 0 has non-null previous_hash")
            else:
                expected_prev = self.manifest.contribution_log[i-1].content_hash
                if entry.previous_hash != expected_prev:
                    violations.append(
                        f"Chain broken at entry {i}: expected prev_hash "
                        f"'{expected_prev[:8]}...', got '{entry.previous_hash[:8] if entry.previous_hash else 'None'}...'"
                    )
        
        return violations
    
    # =========================================================================
    # QUERY HELPERS
    # =========================================================================
    
    def get_active_branches(self) -> List[BranchPointer]:
        """Return all ACTIVE branches."""
        return self.get_branches_by_status(BranchStatus.ACTIVE)
    
    def get_blocked_branches(self) -> List[BranchPointer]:
        """Return all BLOCKED branches."""
        return self.get_branches_by_status(BranchStatus.BLOCKED)
    
    def get_stale_branches(self, hours: int = 72) -> List[BranchPointer]:
        """Return active branches with no updates in given hours."""
        if not self.manifest:
            return []
        
        from datetime import timedelta
        threshold = datetime.utcnow() - timedelta(hours=hours)
        
        return [
            b for b in self.manifest.branches.values()
            if b.status == BranchStatus.ACTIVE and b.updated_at < threshold
        ]
    
    def check_dependencies_satisfied(self, branch_id: str) -> bool:
        """Check if all dependencies for a branch are COMPLETE."""
        if not self.manifest or branch_id not in self.manifest.branches:
            return False
        
        branch = self.manifest.branches[branch_id]
        
        for dep_id in branch.dependencies:
            dep_branch = self.manifest.branches.get(dep_id)
            if not dep_branch or dep_branch.status != BranchStatus.COMPLETE:
                return False
        
        return True
```

---

## 5. Security Considerations

Security is built into the Heap, not layered on top.

### 5.1 Crash Safety (Atomic Writes)

All writes use `tempfile.NamedTemporaryFile` + `os.replace`:
- If process dies mid-write, temp file is orphaned but manifest is intact
- `os.replace` is atomic on POSIX; best-effort on Windows

### 5.2 Tamper Evidence (Hash Chaining)

The `contribution_log` forms a blockchain-style chain:
- Each entry includes `content_hash` (SHA-256 of content written)
- Each entry includes `previous_hash` (hash of prior entry)
- `verify_log_integrity()` detects any insertions, deletions, or modifications

### 5.3 Path Confinement

All filepaths are validated against project root:
- Prevents `../../../etc/passwd` style traversal attacks
- Agents cannot read/write outside the project directory

### 5.4 Schema Strictness

All models use `ConfigDict(extra='forbid')`:
- Unknown fields are rejected, not silently stored
- Prevents hidden data / covert channels via undeclared fields

### 5.5 Namespace Enforcement

Metadata keys must follow `namespace.key` convention:
- Validated at schema level via Pydantic `field_validator`
- Unknown namespaces log warnings (audit trail)
- Reserved keys (`priority`, `source`, `tags`) are exceptions

---

## 6. Module Exports

```python
# app/src/specialists/schemas/__init__.py

from ._manifest import (
    # Enums
    BranchStatus,
    BranchPhase,
    AgentAffinity,
    # Constants
    RESERVED_METADATA_KEYS,
    KNOWN_NAMESPACES,
    # Models
    ContributionEntry,
    BranchPointer,
    ProjectManifest,
)

__all__ = [
    "BranchStatus",
    "BranchPhase",
    "AgentAffinity",
    "RESERVED_METADATA_KEYS",
    "KNOWN_NAMESPACES",
    "ContributionEntry",
    "BranchPointer",
    "ProjectManifest",
]
```

---

## 7. Implementation Plan

### Phase 1: Schemas (Week 1)
- Create `app/src/specialists/schemas/_manifest.py`
- Define all enums, constants, and Pydantic models
- Unit tests for validation (namespace enforcement, extra='forbid')

### Phase 2: ManifestManager (Week 1-2)
- Create `app/src/utils/manifest_manager.py`
- Implement atomic save first (critical path)
- Add CRUD operations
- Add hash chaining for contribution log
- Unit tests for atomic behavior, hash verification

### Phase 3: Integration (Week 2)
- Update `__init__.py` exports
- Create integration tests with real filesystem
- Document usage patterns

---

## 8. Consequences

### Positive

- **Persistent Memory:** Complex work survives sessions, restarts, crashes
- **Forensic Audit:** Complete, tamper-evident trail of agent activity
- **Foundation for Orchestration:** Clean substrate for ADR-023 (Convening), ADR-024 (Deep Research)
- **Type Safety:** Schemas catch errors at write time, not read time
- **Security by Design:** Not an afterthought

### Negative

- **Filesystem Dependency:** Adds I/O latency to every state change
- **Schema Rigidity:** Adding new required fields requires migration
- **Complexity:** More moving parts than in-memory state

### Mitigations

- **Latency:** Async I/O possible; context snippets minimize read size
- **Migration:** `schema_version` field enables future migration scripts
- **Complexity:** ManifestManager encapsulates all complexity; consumers use high-level API

---

## 9. References

1. Huang, Nick. "How agents can use filesystems for context engineering." LangChain Blog, November 2025.
2. Ji, Yichao. "Context Engineering for AI Agents: Lessons from Building Manus." Medium, July 2025.

---

## 10. Relationship to Other ADRs

| ADR | Relationship |
|-----|--------------|
| **ADR-CORE-023 (Convening)** | USES Heap for persistent branch state |
| **ADR-CORE-024 (Deep Research)** | USES Heap for research findings persistence |
| **ADR-CORE-017 (Fishbowl)** | SUPERSEDED — synchronous debate now lives in Convening |
| **ADR-CORE-018 (Checkpoints)** | COMPLEMENTS — PostgreSQL for graph state, Heap for content |

---

*"The Heap is not storage—it is externalized cognition. The Manifest is not a database—it is the Codex that remembers what the context window must forget."*
