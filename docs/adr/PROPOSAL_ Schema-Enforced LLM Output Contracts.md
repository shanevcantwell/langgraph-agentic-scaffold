\#\#\# \*\*PROPOSAL: Schema-Enforced LLM Output Contracts\*\*

\*   \*\*Status:\*\* Draft  
\*   \*\*Author:\*\* Senior Systems Architect  
\*   \*\*Date:\*\* 2025-08-17

\---

\#\#\# 1\. Executive Summary

This document proposes a significant architectural enhancement to our multi-agent system: the adoption of \*\*Schema-Enforced LLM Output Contracts\*\*. The current system relies on a "soft contract" where the desired JSON output format is described in natural language within a specialist's prompt. While functional, this approach is inherently brittle and has led to contract violations where the LLM produces malformed or incomplete JSON.

The proposed solution is to implement a "hard contract" mechanism. This will be achieved by defining the expected output schemas using Pydantic models within our Python code. The LLM client layer will be upgraded to be "schema-aware," automatically translating these Pydantic models into the provider-specific JSON Schema format for any API that supports this feature (e.g., OpenAI-compatible endpoints like LM Studio).

This change will dramatically increase the reliability of our specialists, reduce validation boilerplate, improve the developer experience, and offload the burden of schema compliance from our application to the LLM provider's infrastructure.

\#\#\# 2\. Problem Statement

The current system's reliability is fundamentally limited by the instruction-following capability of the underlying LLM. We have observed several failure modes directly related to this "soft contract" approach:

\*   \*\*Schema Violation:\*\* The \`WebBuilder\` specialist failed when the LLM returned a valid JSON object that was missing the required \`html\_document\` key. This required adding defensive \`try...except KeyError\` blocks in the specialist's business logic.  
\*   \*\*Mode Conflict:\*\* The \`GeminiClient\` failed when the model, despite being instructed to produce JSON, attempted to enter a tool-calling mode. This indicates that complex prompts can create ambiguity that API parameters alone cannot resolve.  
\*   \*\*High Validation Overhead:\*\* Each specialist that expects a JSON output must implement its own logic for cleaning, parsing, and validating the LLM's response. This is a violation of the DRY (Don't Repeat Yourself) principle and increases the surface area for bugs.

Relying solely on prompt engineering for structural integrity makes the system fragile and requires constant, reactive tuning rather than proactive, architectural guarantees.

\#\#\# 3\. Proposed Solution

We will transition to a system where the data contract is defined once, in code, and enforced at the API level wherever possible.

1\.  \*\*Pydantic for Schema Definition:\*\* We will use Pydantic \`BaseModel\` classes to define the precise input and output schemas for our specialists. Pydantic is the industry standard in Python for data validation and provides a clear, self-documenting way to define data structures.

2\.  \*\*Schema-Aware LLM Clients:\*\* The \`BaseLLMClient\` interface will be modified to optionally accept a Pydantic model as an \`output\_schema\`.

3\.  \*\*Progressive Enhancement:\*\* Individual clients (\`LMStudioClient\`, \`OllamaClient\`, etc.) will be upgraded to detect this schema. If the provider supports schema enforcement (like OpenAI's \`response\_format\` with \`json\_schema\`), the client will automatically generate the JSON Schema from the Pydantic model and include it in the API call.

4\.  \*\*Graceful Fallback:\*\* If a provider (like Gemini) does not support schema enforcement, the client will ignore the schema and fall back to our current, prompt-based contract. This ensures universal compatibility.

\#\#\# 4\. Architectural Design

\#\#\#\# 4.1. Pydantic Model Definition

Specialists will define their expected output as a Pydantic model.

\*\*Example:\*\* \`src/specialists/web\_builder\_schema.py\`  
\`\`\`python  
from pydantic import BaseModel, Field

class WebBuilderOutput(BaseModel):  
    html\_document: str \= Field(description="The complete, self-contained HTML document as a string.")  
\`\`\`

\#\#\#\# 4.2. \`BaseLLMClient\` Interface Modification

The abstract \`invoke\` method will be updated to accept the schema.

\*\*File:\*\* \`src/llm/clients.py\`  
\`\`\`python  
from pydantic import BaseModel  
from typing import Type \# Add this import

class BaseLLMClient(ABC):  
    \# ... existing code ...  
    @abstractmethod  
    def invoke(self, messages: List\[BaseMessage\], output\_schema: Optional\[Type\[BaseModel\]\] \= None, ...) \-\> Dict\[str, Any\]:  
        pass  
\`\`\`

\#\#\#\# 4.3. Client Implementation (\`LMStudioClient\`)

The \`LMStudioClient\` will be modified to use the schema if provided.

\*\*File:\*\* \`src/llm/clients.py\`  
\`\`\`python  
class LMStudioClient(BaseLLMClient):  
    def invoke(self, messages: List\[BaseMessage\], output\_schema: Optional\[Type\[BaseModel\]\] \= None, ...) \-\> Dict\[str, Any\]:  
        \# ... existing code ...  
        payload \= {  
            "model": self.model,  
            "messages": \[...\],  
            "temperature": temperature,  
        }

        if output\_schema:  
            \# Add schema enforcement if the model supports it  
            payload\["response\_format"\] \= {  
                "type": "json\_object",  
                "schema": output\_schema.model\_json\_schema()  
            }  
          
        \# ... rest of the invocation logic ...  
\`\`\`

\#\#\#\# 4.4. Specialist Refactoring (\`WebBuilder\`)

The specialist's code becomes dramatically simpler and more declarative.

\*\*File:\*\* \`src/specialists/web\_builder.py\`  
\`\`\`python  
from .web\_builder\_schema import WebBuilderOutput \# Import the schema

class WebBuilder(BaseSpecialist):  
    def execute(self, state: GraphState) \-\> Dict\[str, Any\]:  
        \# ... existing code ...  
        try:  
            \# ... message preparation ...  
              
            \# The client now guarantees the output schema  
            response\_data \= self.llm\_client.invoke(messages, output\_schema=WebBuilderOutput)  
              
            \# No need to check for the key; Pydantic and the client already did.  
            validated\_output \= WebBuilderOutput(\*\*response\_data)

            logger.info("Successfully generated and validated HTML artifact.")  
            return {"html\_artifact": validated\_output.html\_document, "error": None}

        except LLMInvocationError as e:  
            \# ... error handling ...  
        \# The KeyError exception handler is no longer needed for schema violations.  
\`\`\`

\#\#\# 5\. Impact Analysis

\*   \*\*Benefits:\*\*  
    \*   \*\*Increased Reliability:\*\* Shifts the burden of schema compliance to the LLM provider, resulting in far fewer runtime errors.  
    \*   \*\*Reduced Boilerplate:\*\* Eliminates the need for repetitive \`try...except KeyError\` blocks and manual validation in specialists.  
    \*   \*\*Improved Developer Experience:\*\* Provides a single, self-documenting source of truth (the Pydantic model) for each data contract.  
    \*   \*\*Enhanced Performance:\*\* May reduce token usage as the schema is passed out-of-band rather than in the prompt.

\*   \*\*Risks & Mitigations:\*\*  
    \*   \*\*Provider Incompatibility:\*\* Not all providers support this feature.  
    \*   \*\*Mitigation:\*\* The design uses graceful fallback. The \`output\_schema\` is optional, and clients that don't support it will simply ignore it, reverting to the existing prompt-based contract.

\#\#\# 6\. Phased Implementation Plan

1\.  \*\*Phase 1: Core Infrastructure:\*\*  
    \*   Update the \`BaseLLMClient\` interface.  
    \*   Create Pydantic models for \`SystemsArchitect\` and \`WebBuilder\` outputs.

2\.  \*\*Phase 2: Pilot Implementation:\*\*  
    \*   Update the \`LMStudioClient\` to be schema-aware.  
    \*   Refactor the \`SystemsArchitect\` and \`WebBuilder\` specialists to use the new \`output\_schema\` parameter when invoking the client.

3\.  \*\*Phase 3: Full Rollout:\*\*  
    \*   Investigate and implement schema enforcement for other clients (\`OllamaClient\`, etc.) as their capabilities allow.

\#\#\# 7\. Conclusion

Adopting Schema-Enforced LLM Output Contracts is a strategic investment in the reliability and maintainability of our system. It represents a move from a prototype-level, best-effort approach to a production-grade, contract-driven architecture. This change will reduce errors, simplify development, and provide a more robust foundation for future expansion.  
