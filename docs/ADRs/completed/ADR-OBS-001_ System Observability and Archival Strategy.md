# **ADR-OBS-001: System Observability and Archival Strategy**

**Status:** Completed
** * *Date: * * 2025-10-01**

---

## **Context**

The agentic system requires a robust, reliable, and complete record of each execution run for effective debugging, post-mortem analysis, and long-term observability. The previous, ad-hoc approach to generating a final report ( `archive _report.md `) has revealed several architectural deficiencies:

1 .    * *Fragile Data Contracts: * * The termination sequence relied on implicit contracts. For example, the  `response _synthesizer _specialist ` would hallucinate content when functional specialists failed to provide  `user _response _snippets `, indicating a lack of enforceable data flow.

2 .   * *Low-Fidelity Artifacts: * * The practice of embedding structured data (JSON, HTML) within a single Markdown file degraded the usability of these artifacts, preventing the use of native tooling. Furthermore, the truncation of data ( `... `) rendered the reports unreliable for forensic analysis.

3 .   * *No Asset Management Strategy: * * The system lacked a formal contract for handling non-textual assets (e.g., images), creating a high risk of generating artifacts with broken internal references (e.g., an  ` <img > ` tag with an invalid  `src `).

4 .   * *Monolithic and Rigid Design: * * The logic for creating the final report was encapsulated in a single-purpose  `ArchiverSpecialist `. This design was inflexible, not reusable by other components, and tightly coupled the  *what * (the report content) with the  *how * (the file I/O).

A formal, architecturally sound strategy is required to address these issues and establish a professional standard for system observability.

## Decision

We will adopt a comprehensive, tool-based strategy for system archival centered on the principle of a portable, high-fidelity, atomic output. This strategy is composed of the following key decisions:

### 1 . The "Atomic Archival Package" Mandate

The definitive, standard output of every agentic run will be a single, compressed  * * `.zip ` file * *. This file, named  `run _ <timestamp > _ <run _id >.zip `, represents the complete and atomic record of the run. This approach ensures maximum portability and guarantees that the run record is never incomplete.

### 2 . The Archival Package Structure

The  `.zip ` file will contain a well-defined directory structure. This structure separates the human-readable manifest from the raw data artifacts, all of which are stored in their native formats.

/run _ _/   
├──  _archive _report.md  # The human-readable manifest and entry point.   
├── final _state.json  # The complete, unabridged final GraphState.   
├── final _user _response.md  # The final response synthesized for the user.   
├── artifact _  # Example: artifact _webpage.html   
├── artifact _  # Example: artifact _analysis.csv   
└── .  # Example: f4a1b2c3-1a2b-3c4d-4e5f-6a7b8c9d0e1f.png

### 3 . The  ` _archive _report.md ` Schema

The manifest file is the primary interface for a human reviewing the run. It will not embed large data blobs but will instead use relative links to the other files within the package.

 ` ` `markdown

 # Archive Report

 # # 1 . Run Metadata

 -  * *Run ID: * *  <run _id >

 -  * *Start Time (UTC): * * YYYY-MM-DD HH:MM:SS

 -  * *End Time (UTC): * * YYYY-MM-DD HH:MM:SS

 -  * *Final Status: * * (COMPLETED | FAILED)

 # # 2 . Initial Prompt

 > (The full, original user prompt.)

 # # 3 . Final User Response

 -  [View Final User Response ](./final _user _response.md)

 # # 4 . Artifacts Generated

 -  [ ` <artifact _name _1 > ` ](./artifact _ <artifact _name _1 >)

 -  [ ` <artifact _name _2 > ` ](./artifact _ <artifact _name _2 >)

 # # 5 . Specialist Execution Trace

| Turn | Specialist | Rationale / Outcome |  
|---|---|---|  
| ... | ... | ... |

 # # 6 . Diagnostic Data

 -  [View Complete Final GraphState (JSON) ](./final _state.json)  
 ` ` `

### 4 . The "Asset Ingestion and Referencing Contract"

To guarantee referential integrity for assets, we will implement a system-wide contract:

1. **New State Field:** The `GraphState` `TypedDict` will be augmented with a new field: `assets: Dict[str, bytes]`.  
2. **Producer Responsibility:** Any specialist that ingests or generates a binary asset (e.g., an image) MUST: a. Generate a unique, GUID-based filename for the asset (e.g., `f4a1b2c3-....png`). b. Store the asset's raw binary data in the `state["assets"]` dictionary with the unique filename as the key. c. Pass this unique filename to any downstream consumer specialists.  
3. **Consumer Responsibility:** Any specialist that references an asset (e.g., `web_builder` creating an `<img>` tag) MUST use the exact unique filename provided.   
4.  [svc: we have at least one agent that uses hard coded filenames, or probably just produces a fixed filename despite the possibility of being called multiple times to produce different documents ]

This contract ensures that links within generated artifacts will be valid within the context of the unzipped archival package.

### 5 . Decommissioning and Refactoring of Specialists

The implementation of this strategy will be achieved through a significant refactoring of component responsibilities:

1. **Decommission `ArchiverSpecialist`:** The monolithic `ArchiverSpecialist` will be removed from the system.  
2. **Enhance `FileSpecialist`:** The `FileSpecialist` will be promoted to a core system utility, providing a set of composable, tool-based file system operations (e.g., `write_file`, `create_directory`, `create_zip_from_directory`).  
3. **Refactor `EndSpecialist`:** The `EndSpecialist` will be refactored from a procedural component into a **tool-based orchestrator**. Its sole responsibility is to execute a deterministic sequence of tool calls against the `FileSpecialist` to assemble and package the final archive according to the structure defined above.

## Consequences

### Positive

- **High Fidelity:** Run archives will be complete, unabridged, and stored in native formats, dramatically improving the efficiency of debugging and analysis.  
- **Robust Asset Handling:** The system will be able to reliably manage and reference binary assets, a critical capability for advanced use cases.  
- **Increased Modularity and Reusability:** Decomposing archival logic into tools makes file system operations a reusable, system-wide capability.  
- **Clear Architectural Contracts:** The responsibilities of all components in the termination and archival sequence are now explicit, documented, and enforceable.

### Negative

- **Increased Implementation Complexity:** This is a significant refactoring effort. Enhancing `FileSpecialist` and redesigning `EndSpecialist` requires more initial development than the previous monolithic approach.  
- **Platform Dependency:** This entire strategy is contingent on the successful implementation of a persistent, writable filesystem for the application container, as specified in `ADR-PLATFORM-001`.  
- **State Management Overhead:** The new `assets` field in `GraphState` must be correctly managed and passed through the graph, adding a minor degree of complexity.

