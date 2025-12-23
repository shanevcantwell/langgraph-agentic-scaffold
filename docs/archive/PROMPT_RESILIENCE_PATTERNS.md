# Prompt Escape Hatch Manifest

This manifest outlines the necessary changes to specialist prompts to implement robust "Escape Hatch" protocols. These protocols prevent hallucination and system failures by empowering agents to handle ambiguity, missing context, and errors gracefully.

## 1. File Operations Specialist (`app/prompts/file_operations_prompt.md`)

**Current Risk:**
- Fails when requested to perform operations on files that don't exist (e.g., "search n-z folder") if it doesn't know the filenames.
- Lacks explicit instruction to use `gathered_context` (directory listings) to iterate or discover targets.
- May hallucinate filenames if not explicitly found.

**Proposed Escape Hatch:**
- **Context Awareness:** Explicitly instruct the agent to cross-reference user requests with `gathered_context`. If a user asks to "search folder X", and `gathered_context` lists files `A, B, C` in folder X, the agent must infer it should read `A, B, and C`.
- **Graceful Failure:** If a file is missing, report "File not found: [filename]" and continue with other operations if possible, or stop and report the specific error. Do not crash.
- **Ambiguity Handling:** If the target is ambiguous (e.g., "the file"), and context lists multiple candidates, ask for clarification or list the candidates.

**Action:** Update `app/prompts/file_operations_prompt.md` with a "Context Utilization & Escape Hatch" section.

## 2. Router Specialist (`app/prompts/router_prompt.md`)

**Current Risk:**
- May force a route to a specialist even if none are a perfect fit, leading to "square peg in round hole" failures.
- Might route to a specialist that just failed (loops).

**Proposed Escape Hatch:**
- **No-Fit Protocol:** If no specialist matches the request, or if the request is "I don't know what to do", route to `default_responder_specialist` (or `chat_specialist`) with a clear instruction to explain the limitation to the user.
- **Loop Prevention:** Explicitly check `routing_history`. If the last specialist failed or produced no result, do NOT route to it again. Route to `default_responder_specialist` to ask for user help.

**Action:** Update `app/prompts/router_prompt.md` to strengthen the "Handle Failure and Fallback" rule and add a "No-Fit" clause.

## 3. Web Builder Specialist (`app/prompts/web_builder_prompt.md`)

**Current Risk:**
- Hallucinating design requirements when the user request is vague (e.g., "build a dashboard").
- attempting to build without a `system_plan` when one is needed for complexity.

**Proposed Escape Hatch:**
- **Requirement Check:** If the request lacks specific design details (colors, layout, components), do NOT guess.
- **Plan Dependency:** If the task is complex (>1 component), explicitly state "I need a system plan first" and route (via Router logic) or ask the user to provide more detail.

**Action:** Update `app/prompts/web_builder_prompt.md` with a "Requirements Validation" section.

## 4. Data Extractor Specialist (`app/prompts/data_extractor_prompt.md`)

**Current Risk:**
- Hallucinating data to fit a schema when the source text is missing the information.
- Returning "N/A" without explanation.

**Proposed Escape Hatch:**
- **Truthfulness Protocol:** If a field is missing in the source text, leave it null/empty and explicitly note in a "metadata" or "notes" field that the data was missing. Do NOT fabricate data.
- **Schema Mismatch:** If the text doesn't match the expected format at all, report "Data format mismatch" instead of trying to force extraction.

**Action:** Update `app/prompts/data_extractor_prompt.md` with "Truthfulness & Missing Data" instructions.

## 5. Researcher Specialist (`app/prompts/researcher_prompt.md`)

**Current Risk:**
- Hallucinating facts if search results are poor.
- Returning irrelevant search results as "answers".

**Proposed Escape Hatch:**
- **Null Result Handling:** If search returns no relevant results, state "No relevant information found" and suggest 3 alternative search queries.
- **Fact Verification:** Only cite facts present in the search snippets. Do not use internal knowledge to "fill in" unless explicitly asked.

**Action:** Update `app/prompts/researcher_prompt.md` (if it exists as a standalone prompt, otherwise the Triage/Facilitator logic) with "Search Failure Handling".

## Implementation Plan

1.  **Apply Changes:** Sequentially update the prompt files with the new sections.
2.  **Verify:** Run the "Search n-z" test case again to verify `file_operations_specialist` now handles the list correctly.
3.  **Verify:** Run a "vague build" request to test `web_builder` escape hatch.
