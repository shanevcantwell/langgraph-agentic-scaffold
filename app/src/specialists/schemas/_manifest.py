from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field

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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    run_id: str = Field(..., description="Unique identifier for this execution run.")
    routing_history: List[str] = Field(default_factory=list)
    artifacts: List[ArtifactManifest] = Field(default_factory=list)
    final_response_generated: bool
    termination_reason: str = "success"
