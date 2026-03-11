# **Standardized Specialist Self-Correction Mechanism**

* **Status:** Completed  
* **Date:** 2025-09-16  
* **Deciders:** System Architecture Team

---

## **## Context**

Currently, when a specialist encounters a recoverable, internal failure (e.g., its backing LLM fails to generate a valid tool call), there is no standardized way to handle it. The specialist returns a generic error message, which may not provide the RouterSpecialist with enough context to effectively correct the workflow.

This was observed when the file_specialist's LLM failed to produce a valid tool call, causing the workflow to stall without a clear path to recovery. Ad-hoc solutions within each specialist would lead to inconsistent, brittle code that violates the DRY (Don't Repeat Yourself) principle. A formal, system-wide pattern is needed to allow specialists to request a retry with a more refined prompt, enhancing the overall resilience and autonomy of the system.

---

## **## Decision**

We will implement a standardized, cross-specialist **self-correction mechanism**. This pattern will allow any specialist to signal to the RouterSpecialist that it has encountered a recoverable error and requires a retry with a clarifying prompt.

This will be accomplished through the following changes:

**1. A new helper function will be added to app/src/specialists/helpers.py to create a consistent state update object for self-correction requests.**

Python

# app/src/specialists/helpers.py

def create_self_correction_request(specialist_name: str, rationale: str) -> dict:  
    """Creates a standardized state update for a self-correction loop."""  
    return {  
        "self_correction_request": rationale,  
        "retry_specialist": specialist_name,  
    }

**2. A new public method, request_self_correction, will be added to the BaseSpecialist abstract base class.** This makes the pattern discoverable and available to all current and future specialists.

Python

# app/src/specialists/base.py  
from .helpers import create_self_correction_request

class BaseSpecialist(ABC):  
    # ... existing methods ...  
    def request_self_correction(self, rationale: str) -> Dict[str, Any]:  
        """  
        Signals that the specialist has encountered a recoverable error and  
        needs to be retried with a clarifying prompt.  
        """  
        logger.warning(f"Specialist '{self.specialist_name}' is requesting self-correction. Rationale: {rationale}")  
        return create_self_correction_request(self.specialist_name, rationale)

**3. The RouterSpecialist's prioritized decision tree in _execute_logic will be updated to handle this new signal.** This check will have a high priority to ensure self-correction loops are handled immediately.

Python

# app/src/specialists/router_specialist.py

def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:  
    # ... turn_count logic ...

    # Priority 1: A self-correction request is a command to retry immediately.  
    if state.get("self_correction_request") and state.get("retry_specialist"):  
        routing_type = "self_correction_loop"  
        specialist_to_retry = state["retry_specialist"]  
        correction_prompt = state["self_correction_request"]  
          
        correction_message = SystemMessage(  
            content=f"ATTENTION: The previous attempt failed. You must try again. Follow this guidance: {correction_prompt}"  
        )  
          
        # Consume the request signals and route back to the specialist  
        return {  
            "messages": [correction_message],  
            "next_specialist": specialist_to_retry,  
            "turn_count": turn_count,  
            "self_correction_request": None,  
            "retry_specialist": None  
        }

    # Priority 2: Fatal error report... (the rest of the logic follows)  
    elif state.get("error_report"):  
        # ...

**4. The GraphState in app/src/graph/state.py will be updated** to include the necessary fields for this mechanism.

Python

# app/src/graph/state.py

class GraphState(TypedDict):  
    # ... existing fields  
    self_correction_request: Optional[str]  
    retry_specialist: Optional[str]

---

## **## Consequences**

### **### Positive:**

* **Increased System Resilience:** The system will be able to autonomously recover from a new class of common LLM failures (e.g., malformed outputs, failure to follow instructions).  
* **Improved Code Quality:** Establishes a clean, reusable, and consistent pattern for handling recoverable errors, adhering to the DRY principle.  
* **Enhanced Agentic Behavior:** Formalizes a key agentic capability (self-correction), making the overall system more intelligent and robust.

### **### Negative:**

* **Risk of Unproductive Loops:** If the underlying issue is persistent (e.g., a consistently incapable LLM or an impossible task), this mechanism could retry multiple times before failing. The existing global loop detection in the ChiefOfStaff should mitigate this risk.  
* **Increased Trace Complexity:** Debugging traces in LangSmith will show these retry loops, which adds a layer of complexity to analysis, though this is also a feature as it makes the correction attempt explicit.