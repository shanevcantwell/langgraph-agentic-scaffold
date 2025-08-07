# [SYSTEM BOOTSTRAP] DEVELOPERS_GUIDE.md
# Project: SpecialistHub
# Version: 1.0
# Status: ACTIVE

## 1.0 CORE DIRECTIVE: MISSION & PHILOSOPHY

**Mission:** To construct a multi-agent system composed of modular, single-responsibility "Specialists." The system must be scalable, maintainable, and testable.

**Core Philosophy:** Specialists are treated as "intelligent objects" or "functional components." They are not conversational partners; they are predictable processors within a larger computational graph. The system prioritizes reliability and machine-to-machine communication over human-like interaction for its internal operations.

## 2.0 ARCHITECTURAL BLUEPRINT

The system is composed of the following layers and components.

### 2.1 LangGraph: The Runtime Environment
*   **Role:** Framework / Execution Engine.
*   **Function:** Manages the computational graph, holds the central `GraphState`, and routes execution between nodes based on their output.
*   **Analogy:** An operating system kernel or a microservices container orchestrator (e.g., Kubernetes). It runs the code; it is not the code itself.

### 2.2 Specialists: The Functional Units
*   **Role:** Agent / Worker / Node.
*   **Contract:** Must inherit from `src.specialists.base.BaseSpecialist`. Must implement the `execute(state: GraphState) -> Dict[str, Any]` method.
*   **Constraint:** A Specialist must have a single, well-defined responsibility.

### 2.3 The Router/Supervisor: The Central Dispatcher
*   **Role:** Orchestrator / Decision Engine.
*   **Implementation:** A dedicated Specialist (`RouterSpecialist`).
*   **Function:** To receive the current `GraphState` and output a machine-readable directive (JSON) indicating the next Specialist node to execute. It is the primary implementation of the "Functional LLM Call" pattern.

### 2.4 LLM Interaction Protocol: `json<-->json`
This is a non-negotiable protocol for all internal system communication.
*   **Type:** Functional / Transactional.
*   **Input:** LLM calls must be provided with a structured prompt that includes a strict JSON schema for the desired output.
*   **Output:** The LLM's response **must** be a valid JSON string, with no extraneous conversational text.
*   **Purpose:** To ensure predictable, parsable, and reliable communication between Specialists. Conversational, natural-language outputs are reserved exclusively for the final, user-facing node.

## 3.0 FILE & NAMING SCHEMA (MANDATORY)

Adherence to this structure is required for system integrity and automated parsing.

### 3.1 Directory Structure

.
├── app/
│   ├── docs/
│   │   └── DEVELOPERS_GUIDE.md # This guide
│   ├── prompts/
│   │   └── {specialist_name}_prompt.md
│   └── src/
│       ├── graph/
│       │   └── state.py
│       ├── llm/
│       │   ├── clients.py
│       │   └── factory.py
│       ├── specialists/
│       │   ├── base.py
│       │   └── {specialist_name}.py
│       └── utils/
│           └── prompt_loader.py
├── .gitignore
├── main.py
├── pyproject.toml
├── README.md
└── requirements.txt

### 3.2 Naming Convention
*   **Rule:** A Python file in `src/specialists/` must be the `snake_case` version of the primary `PascalCase` class it contains.
*   **Example:** The class `DataExtractorSpecialist` must reside in the file `data_extractor_specialist.py`.
*   **Rationale:** Eliminates ambiguity and enables predictable file lookups.

## 4.0 PROTOCOL: CREATING A NEW SPECIALIST

Execute the following sequence to provision a new Specialist.

### 4.1 Step 1: Define Prompt Contract
1.  Create a new file in `src/prompts/`.
2.  Filename must be `{specialist_name}_prompt.txt`.
3.  A completely de-identified prompt for posting to github is named `{specialist_name}_prompt.txt.example`.
4.  Define the system prompt. If the specialist is functional, this prompt **must** include the required input variables and the mandatory output JSON schema. This prompt is an API contract.

### 4.2 Step 2: Implement Specialist Logic
1.  Create a new file in `src/specialists/` following the naming convention in section 3.2.
2.  Use the following template. Do not deviate from this structure.

```python
# [TEMPLATE] src/specialists/{specialist_name}.py

import json
from typing import Dict, Any

from ..utils.prompt_loader import load_prompt
from .base import BaseSpecialist
from ..graph.state import GraphState
from langchain_core.messages import SystemMessage, HumanMessage

class NewSpecialistName(BaseSpecialist):
    """
    [Docstring: State the specialist's single, measurable responsibility.]
    """

    def __init__(self, llm_provider: str):
        # Load the prompt contract.
        system_prompt = load_prompt("{specialist_name}")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        print("---INITIALIZED {NewSpecialistName}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        [Docstring: Describe input keys from state and output keys to state.]
        """
        print(f"---EXECUTING {self.__class__.__name__}---")
        
        # 1. Ingest: Retrieve required data from the GraphState.
        #    Validate presence of required keys.
        
        # 2. Serialize: Construct the message list for the LLM.
        #    For functional calls, the user message is often a JSON string.
        
        # 3. Invoke: Call the LLM.
        #    ai_response_str = self.llm_client.invoke(messages_to_send).content
        
        # 4. Parse & Validate:
        #    - For functional calls, wrap `json.loads(ai_response_str)` in a try/except block.
        #    - Validate the parsed data against the expected schema.
        #    - Implement fallback/retry logic on failure.
        
        # 5. Egress: Return a dictionary containing the new data to be merged into GraphState.
        
        return {} # Placeholder