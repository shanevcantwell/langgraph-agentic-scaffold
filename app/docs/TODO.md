# TODO & Loose Ends

This document tracks the next steps and areas for improvement in the agentic scaffold.

## High Priority

- **[x] Implement Real LLM Clients**: The `GeminiClient` now makes actual API calls to `google.generativeai`.

- **[x] Create `FileSpecialist`**: A `FileSpecialist` has been created in `app/src/specialists/` with methods for file system CRUD operations (`read_file`, `write_file`, `list_directory`). It has been integrated into `main.py` and the `RouterSpecialist` prompt has been updated.

- **[x] Improve `main.py` Input Handling**: The `main.py` script now accepts a user prompt from a command-line argument and provides default behavior if no argument is given.

- **[ ] Enhance Graph Error Handling**: The graph's control flow is currently "happy path."
  - **[x]** What happens if the `RouterSpecialist` returns a specialist name that isn't in the conditional map? The graph will crash. Add a default or error-handling branch. (Implemented `route_to_specialist` function in `main.py` with fallback logic).
  - **[x]** What if an API call fails due to a network error? Implement retry logic in the `BaseLLMClient` or individual clients. (Added `tenacity` retry logic to all clients in `llm/clients.py`)

## Medium Priority
- **[ ] Add Unit and Integration Tests**: Create a `tests/` directory and add tests for specialists and the LLM factory to ensure stability during future refactoring.
