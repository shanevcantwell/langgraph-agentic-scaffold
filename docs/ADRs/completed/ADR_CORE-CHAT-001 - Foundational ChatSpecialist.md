# **ADR: CORE-CHAT-001 - Foundational ChatSpecialist**

**Status:** Completed

Context:  
The agentic scaffold currently lacks a basic, user-facing conversational interface. To "eat our own dogfood" and provide immediate utility, a foundational ChatSpecialist is required. This specialist will serve as the baseline for simple interactions and the entry point for future, more complex conversational subgraphs.  
Decision:  
We will implement a new, standard LLM specialist named ChatSpecialist. This specialist will be responsible for general-purpose conversational responses.  
**Implementation Plan:**

1. **Create Specialist File:** Create app/src/specialists/chat_specialist.py. This class must inherit from BaseSpecialist.  
2. **Create Prompt File:** Create app/prompts/chat_prompt.md. This prompt will instruct the LLM to be a helpful, general-purpose conversational assistant.  
3. **Configure config.yaml:** Register the new specialist in config.yaml:  
   YAML  
   chat_specialist:  
     type: "llm"  
     prompt_file: "chat_prompt.md"  
     description: "A general-purpose conversational specialist for answering user questions and chatting."

4. **Implement _execute_logic:** The ChatSpecialist's _execute_logic method will:  
   * Generate a single AIMessage response based on the messages history.  
   * **Critically**, it must return task_is_complete: True in its state delta. This is mandatory to trigger the EndSpecialist and the three-stage termination sequence, ensuring the chat response is properly synthesized and archived.  
   * It must *also* write its conversational output to scratchpad.user_response_snippets so the EndSpecialist can create the final_user_response.md.  
   * **Return Value:**  
     Python  
     return {  
         "messages": [ai_message],  
         "scratchpad": {"user_response_snippets": [ai_message.content]},  
         "task_is_complete": True  
     }

5. **Graph Integration:** No graph modifications are needed. The RouterSpecialist, guided by the new description in config.yaml, will automatically route conversational prompts to this specialist.

Rationale:  
This provides the simplest, most direct path to prompt --> chatbot --> user. It correctly utilizes the existing termination sequence to ensure chat responses are handled just like any other completed task.

---

