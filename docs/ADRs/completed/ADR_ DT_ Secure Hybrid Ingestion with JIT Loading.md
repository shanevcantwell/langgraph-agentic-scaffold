This analysis provides a comprehensive architectural recommendation for integrating file ingestion into the langgraph-agentic-scaffold (LAS) system. It addresses the identified gaps while adhering to architectural constraints (GraphState reducer, SafeExecutor, token budget) and enabling planned capabilities (Dossier Pattern, MCP integration, Context Engineering).

### **Recommended Architecture: Secure Hybrid Ingestion with JIT Loading**

The optimal architecture is a hybrid model characterized by a secure, multi-stage ingestion process, a centralized metadata registry in GraphState, and Just-In-Time (JIT) content loading via MCP.

### **Implementation Blueprint**

This blueprint addresses the six core design questions.

#### **1\. Ingestion Point: Secure Staging and Dedicated Specialist**

A two-stage ingestion process maximizes security and ensures observability within the graph execution framework.

**Stage 1: API Layer \- Secure Upload and Staging**

* The entry point (FastAPI/Gradio) handles the physical file upload.  
* **Security:** Files MUST be streamed to an isolated **staging area** (e.g., /tmp/staging), strictly separate from the agent workspace (/workspace). Initial validation (size, MIME type) occurs here.  
* **Signaling:** The API layer initializes GraphState and injects a signal into the scratchpad.

Python

\# Initial GraphState signaling example  
initial\_state \= {  
    "scratchpad": {  
        "pending\_ingestion": \[  
            {"temp\_path": "/tmp/staging/uuid1.dat", "original\_filename": "ROADMAP.md", ...}  
        \]  
    }  
}

**Stage 2: FileIngestionSpecialist (New Graph Node)**

* A new, procedural (non-LLM) specialist executed early in the graph.  
* **Responsibilities:**  
  1. Consume the pending\_ingestion signal.  
  2. Perform deeper security validation.  
  3. Securely move the file from the staging area into the agent workspace (e.g., /workspace/files/).  
  4. Extract metadata (checksum, exact size) and determine the Content Strategy.  
  5. Register the file in the GraphState.file\_registry.

#### **2\. Artifact Schema: The FileRegistry and FileArtifact**

To manage token budgets and improve organization, we introduce a dedicated file\_registry in GraphState, separate from generic artifacts.

Python

\# Proposed structure in app/src/graph/state.py  
from typing import TypedDict, Literal, Optional, Annotated, Dict  
import operator

class FileArtifact(TypedDict):  
    artifact\_id: str  \# UUID  
    filename: str  
    workspace\_path: str  \# Secure path for MCP access  
    size\_bytes: int  
    mime\_type: str  
    checksum: str  
    security\_status: Literal\["validated", "flagged"\]

    \# Content Strategy: Manages token budget and access patterns  
    strategy: Literal\["reference", "embedded", "preview", "summarized"\]

    \# Optional fields based on strategy:  
    content\_embedded: Optional\[str | bytes\]  \# Only for small, critical files  
    content\_preview: Optional\[str\] \# First N characters  
    content\_summary: Optional\[str\]   \# Populated later by Context Engineering

class GraphState(TypedDict):  
    \# ... other fields ...  
    \# New: Centralized registry for file metadata, keyed by artifact\_id  
    file\_registry: Annotated\[Dict\[str, FileArtifact\], operator.ior\]

The FileIngestionSpecialist sets the initial strategy based on configurable thresholds for file size and type.

#### **3\. Discovery API: BaseSpecialist Helpers**

Specialists discover files by inspecting GraphState. Helper methods in BaseSpecialist provide a clean abstraction.

Python

\# In app/src/specialists/base.py

class BaseSpecialist:  
    \# ...  
    def get\_file\_registry(self, state: GraphState) \-\> Dict\[str, FileArtifact\]:  
        """Discovery API: Returns the full file registry metadata."""  
        return state.get("file\_registry", {})

    def get\_file\_artifact(self, state: GraphState, artifact\_id: str) \-\> Optional\[FileArtifact\]:  
        """Lookup API: Retrieves a specific artifact by ID."""  
        return state.get("file\_registry", {}).get(artifact\_id)

#### **4\. ChatSpecialist Integration: JIT Loading and Context Engineering**

Integration relies on prompt injection for awareness and JIT loading for access, leveraging the planned Context Engineering subgraph.

**Prompt Injection:** Prompts for key specialists (Router, ChatSpecialist, TriageArchitect) are updated to include summaries derived from the file\_registry (filename, size, preview, summary).

Just-In-Time (JIT) Loading Helper:  
A helper in BaseSpecialist abstracts the content access strategy, handling embedded content or fetching referenced content synchronously via MCP.

Python

\# In BaseSpecialist  
    def load\_artifact\_content(self, artifact: FileArtifact) \-\> str | bytes | None:  
        """JIT Loading mechanism."""  
        strategy \= artifact.get("strategy")

        if strategy \== "embedded" and artifact.get("content\_embedded"):  
            return artifact.get("content\_embedded")

        \# If referenced, or if embedded content is missing, fetch via MCP  
        if not self.mcp\_client:  
            \# Handle error: MCP unavailable  
            return None

        \# Use call\_safe for robustness (Developer's Guide 4.5.6)  
        success, content \= self.mcp\_client.call\_safe(  
            "file\_specialist",  
            "read\_file",  
            path=artifact.get("workspace\_path")  
        )  
        \# ... (Error handling if not success) ...  
        return content if success else None

**Context Engineering (Roadmap Workstream 5):** For large files, the TriageArchitect (Task 5.1) identifies relevant files. The Summarizer (Task 5.3) uses JIT loading to process the file and updates the artifact's content\_summary, which is then used by the consumer specialist.

#### **5\. MCP Role: Synchronous I/O Provider**

This architecture reinforces the existing design (Roadmap Task 2.6):

* **MCP (FileSpecialist):** Remains the sole provider of synchronous, deterministic file I/O. It is the secure gateway to the filesystem used by the JIT loader and the FileIngestionSpecialist.  
* **Graph Nodes:** Handle orchestration, state management, and complex processing.

#### **6\. Dossier Preparation: Handoff by Reference**

To align with the Dossier pattern (Roadmap Tasks 2.1-2.4) and manage state size, handoffs must use references (Artifact IDs), not embedded content.

Python

\# Specialist A (Sender) implementation  
dossier \= {  
    "recipient": "SpecialistB",  
    "message": "Please analyze the attached roadmap.",  
    \# The payload\_key refers to the artifact\_id in GraphState.file\_registry  
    "payload\_key": "UUID-1234-..."  
}  
\# return {"scratchpad": {"dossier": dossier}}

The recipient (Specialist B) uses the BaseSpecialist helpers (get\_file\_artifact and load\_artifact\_content) to access the metadata and JIT-load the content as needed.