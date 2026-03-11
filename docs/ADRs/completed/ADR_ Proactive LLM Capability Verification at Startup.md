# **Proactive LLM Capability Verification at Startup**

* **Status:** Completed  
* **Date:** 2025-09-16  
* **Deciders:** System Architecture Team

---

## **## Context**

Runtime failures have been observed when a specialist is bound to an LLM provider that lacks the necessary capabilities for its task (e.g., an LLM that cannot reliably perform tool-calling for the file_specialist). Currently, these misconfigurations are only discovered during a live workflow, leading to unpredictable stalls and failures.

To enhance system robustness, we need a mechanism to "shift-left" this failure detection. This involves verifying that an LLM's capabilities match a specialist's requirements at application startup, rather than at runtime.

---

## **## Decision**

We will implement a proactive capability verification system that runs during the ChiefOfStaff's specialist loading process. This check will be controllable via a new setting in config.yaml and will programmatically disable specialists whose assigned LLMs fail the verification, preventing the system from starting in a broken state.

### **### 1. Configuration in config.yaml**

A new section will be added to config.yaml under workflow to enable or disable this feature. This provides developers with an escape hatch to speed up startup during rapid prototyping if needed.

**Proposed config.yaml change:**

YAML

# config.yaml

workflow:  
  # ... existing settings like entry_point, max_loop_cycles ...

  # --- NEW: Capability Verification Settings ---  
  # Enable or disable the proactive LLM capability check at startup.  
  # Disabling this can speed up startup but risks runtime failures if an  
  # LLM is misconfigured for a specialist's needs.  
  enable_capability_check: true

**Justification:** Placing this toggle in config.yaml makes it a deliberate, developer-level architectural choice that is version-controlled with the rest of the system's blueprint.

### **### 2. The Specialist Contract in base.py**

The BaseSpecialist class will be updated with an enum and a new property to create a formal contract for specialists to declare their LLM capability requirements.

**Proposed base.py changes:**

Python

# app/src/specialists/base.py  
from enum import Enum  
from typing import List

class LLMCapability(str, Enum):  
    TOOL_CALLING = "TOOL_CALLING"

class BaseSpecialist(ABC):  
    # ... existing methods ...

    @property  
    def required_llm_capabilities(self) -> List[LLMCapability]:  
        """Specifies the capabilities this specialist requires from its LLM."""  
        return []

**Justification:** This abstract property establishes a clear, discoverable contract, ensuring that the capability requirements are defined alongside the specialist's core logic.

### **### 3. The Capability Prober Utility**

A new utility will be created to contain the "canary request" logic, centralizing the testing mechanism and keeping the ChiefOfStaff focused on orchestration.

**Proposed new file app/src/utils/capability_prober.py:**

Python

# app/src/utils/capability_prober.py  
import logging  
from pydantic import BaseModel  
from typing import List  
from ..llm.adapter import BaseAdapter, StandardizedLLMRequest  
from ..specialists.base import LLMCapability

logger = logging.getLogger(__name__)

class _CanaryTool(BaseModel):  
    """A simple tool for the canary request."""  
    param: str = "value"

def probe_llm_capabilities(adapter: BaseAdapter, capabilities: List[LLMCapability]) -> bool:  
    """Sends a simple request to an LLM to verify it can perform a required task."""  
    if not capabilities:  
        return True

    for capability in capabilities:  
        if capability == LLMCapability.TOOL_CALLING:  
            logger.info(f"Probing '{adapter.model_name}' for capability: {capability.value}")  
            request = StandardizedLLMRequest(  
                messages=[("human", "Call the tool.")],  
                tools=[_CanaryTool],  
                force_tool_call=True  
            )  
            response = adapter.invoke(request)  
            if not response.get("tool_calls"):  
                logger.error(f"Capability check FAILED for '{adapter.model_name}': Did not produce a tool call when forced.")  
                return False  
      
    logger.info(f"Capability checks PASSED for '{adapter.model_name}'.")  
    return True

**Justification:** This utility encapsulates the specific logic for how to test a capability, decoupling it from the orchestration logic in the ChiefOfStaff.

### **### 4. Integration into ChiefOfStaff**

The ChiefOfStaff will be updated to read the new configuration setting and execute the capability probe during specialist loading.

**Proposed chief_of_staff.py changes:**

Python

# app/src/workflow/chief_of_staff.py  
from ..utils.capability_prober import probe_llm_capabilities

class ChiefOfStaff:  
    def __init__(self):  
        # ...  
        self.workflow_config = self.config.get("workflow", {})  
        self.enable_capability_check = self.workflow_config.get("enable_capability_check", False)  
        # ...

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:  
        # ... (inside the for loop) ...  
        try:  
            # ... (after instantiating specialist) ...

            if binding_key := config.get("llm_config"):  
                # ... (code to create the adapter) ...  
                instance.llm_adapter = self.adapter_factory.create_adapter(...)

                if self.enable_capability_check:  
                    if not probe_llm_capabilities(instance.llm_adapter, instance.required_llm_capabilities):  
                        logger.error(  
                            f"Disabling specialist '{name}' because its LLM "  
                            f"'{instance.llm_adapter.model_name}' failed capability checks."  
                        )  
                        continue # Skip to the next specialist in the loop.

            loaded_specialists[name] = instance  
            # ...

**Justification:** This integrates the check into the existing startup lifecycle. It respects the developer's choice via the config toggle and ensures that only fully verified specialists are added to the final, compiled graph.

---

## **## Consequences**

### **### Positive:**

* **Prevents Runtime Failures:** Catches fundamental misconfigurations at startup, making the system more reliable.  
* **Improves Developer Experience:** Provides clear, immediate feedback if an LLM is unsuitable for a specialist's task.  
* **Enforces Architectural Integrity:** Ensures that the bindings in user_settings.yaml are not just syntactically correct, but functionally viable.

### **### Negative:**

* **Increased Startup Time:** The capability check introduces a slight delay at startup due to the "canary" LLM calls. The enable_capability_check flag allows this to be disabled when not needed.  
* **Dependency on LLM Server Availability:** The application will not start correctly if a required LLM provider is offline during the startup check.