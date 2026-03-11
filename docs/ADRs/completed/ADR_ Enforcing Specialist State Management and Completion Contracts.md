# **ADR: Enforcing Specialist State Management and Completion Contracts** 

## Proposed Date: 2025-09-21 Author: Gemini Code Assist**
## **Status: Completed

1. Context A review of the current specialist implementations has revealed several deviations from the established architectural patterns for state management and workflow control. Specifically:

Inconsistent Task Completion: The PromptSpecialist, OpenInterpreterSpecialist, and DataExtractorSpecialist are hardcoding task_is_complete: True in their return state. This violates the Three-Stage Termination Pattern (DEVELOPERS_GUIDE.md, Section 4.3), which mandates that task completion should be a deliberate, high-level decision, typically made by a gatekeeper like the CriticSpecialist or by the RouterSpecialist when a plan is fulfilled. This premature signaling short-circuits complex workflows and prevents multi-step execution. Violating the "Return Deltas" Contract: The DataProcessorSpecialist and FileSpecialist are manually re-adding the entire messages list to their return state ("messages": state["messages"] + [new_message]). The GraphState is explicitly configured with Annotated[List[BaseMessage], operator.add], meaning the graph itself is responsible for appending messages. This manual re-addition is redundant and can lead to duplicated messages if the graph's behavior changes. Misuse of task_is_complete: The TextAnalysisSpecialist attempts to infer whether it's part of a larger plan by checking for the existence of a system_plan artifact. This is brittle and duplicates logic that belongs in the orchestration layer. A specialist's role is to perform its task and report its output, not to guess its position in the overall workflow. These inconsistencies make the system's behavior difficult to predict and debug.

2. Decision We will refactor the identified specialists to strictly adhere to the established architectural contracts. This will restore predictable control flow and reinforce the separation of concerns between functional specialists and the orchestration layer.

Remove Premature Completion Signals: The task_is_complete flag will be removed from PromptSpecialist, OpenInterpreterSpecialist, DataExtractorSpecialist, and TextAnalysisSpecialist. These specialists will now simply perform their function and return their output, allowing the RouterSpecialist or other orchestrators to determine the next step. Enforce "Return Deltas" Contract: The DataProcessorSpecialist and FileSpecialist will be modified to return only the new message they generate. The graph's operator.add annotation on the messages state field will handle the append operation correctly. Simplify TextAnalysisSpecialist: The complex logic for inferring task completion and managing user_response_snippets will be removed. The specialist will now simply perform its analysis and add its report to the artifacts dictionary. 3. Implementation & Rectification The following changes will be made to the respective specialist files.

File: app/src/specialists/prompt_specialist.py

Change: Remove task_is_complete: True. Rationale: The PromptSpecialist should not assume it is the final step. It should return its answer and let the Router decide if the conversation is over. prompt_specialist.py -1 +1 llm_adapter=self.llm_adapter, content=text_response, ) return {"messages": [ai_message], "task_is_complete": True} return {"messages": [ai_message]}

File: app/src/specialists/open_interpreter_specialist.py

Change: Remove task_is_complete: True. Rationale: Executing code is often one step in a larger plan. The specialist should report the result of the execution and allow the Router to proceed with the next step in the plan or terminate if the task is done. open_interpreter_specialist.py -1 +1 content=f"I have executed the following {code_params.language} code:nn`n{code_params.code}n`nn**Result:**n{final_output}", )

    return {"messages": [ai_message], "task_is_complete": True}

    return {"messages": [ai_message]}

File: app/src/specialists/data_extractor_specialist.py

Change: Remove the logic that infers and sets task_is_complete. Rationale: Similar to other specialists, the DataExtractor should focus solely on its task of extraction. The Router is responsible for determining if this extraction completes the overall user goal. data_extractor_specialist.py -6 +0 Show full code block content=f"I have successfully extracted the following data: {extracted_data}", )

    # The task is only complete if this specialist was not part of a larger plan.

    # The presence of a 'system_plan' artifact is the key indicator.

    is_part_of_larger_plan = state.get("system_plan") is not None

    task_is_complete = not is_part_of_larger_plan

    return {

        "messages": [ai_message],

        "extracted_data": extracted_data,

        "task_is_complete": task_is_complete

    }

File: app/src/specialists/text_analysis_specialist.py

Change: Remove the logic that infers and sets task_is_complete and manages user_response_snippets. Rationale: This simplifies the specialist significantly, making it a pure "analyzer" that produces an artifact. The ResponseSynthesizer is already capable of inferring the final response from the last message if no snippets are provided. text_analysis_specialist.py -11 +0 Show full code block content=report, )

    # --- MODIFICATION: ADOPT THE "FINAL ANSWER" PATTERN ---

    # The task is only complete if this specialist was not part of a larger plan.

    # The presence of a 'system_plan' artifact is a key indicator of a larger plan.

    is_part_of_larger_plan = state.get("artifacts", {}).get("system_plan") is not None

    task_is_complete = not is_part_of_larger_plan

    updated_state = {

        "messages": [ai_message],

        "artifacts": { "text_analysis_report.md": report },

        "task_is_complete": task_is_complete

    }

    # If this IS the final answer, add the report to the snippets for the user.

    if task_is_complete:

        updated_state["scratchpad"] = { "user_response_snippets": [report] }

    return updated_state

File: app/src/specialists/data_processor_specialist.py

Change: Return only the new message, not the entire history. Rationale: Adheres to the "Return Deltas" contract, relying on the graph to manage state appends. data_processor_specialist.py -1 +1 Show full code block

    new_message = AIMessage(content="I have processed the data artifact.")

    return {

        "messages": state["messages"] + [new_message],

        "messages": [new_message],

        "processed_data": data

    }

4. Consequences Positive: Predictable Control Flow: The RouterSpecialist and ChiefOfStaff regain full control over workflow termination, making the system's behavior consistent and easier to reason about. Improved Modularity: Specialists are now simpler and more focused on their single responsibility, adhering to the "S" in SOLID principles. Reduced Bugs: Eliminates a class of bugs where simple, single-step tasks would cause the entire workflow to terminate prematurely. Architectural Integrity: The codebase now correctly reflects the documented architectural patterns. Negative: None. This change corrects a deviation from the intended architecture and has no known negative side effects.

