# TODO: Consolidate `agents` and `specialists` Directories

## Status: Completed by Gemini Code Assist 2025-08-07

## Objective
Unify the codebase by moving all agent-related code into the `src/specialists` directory and deleting the redundant `src/agents` directory.

## Rationale
The current file structure has two directories (`src/agents` and `src/specialists`) representing the same concept. This violates the "single source of truth" principle defined in `DEVELOPERS_GUIDE.md` and creates confusion. We will standardize on the term **Specialist**.

## Step-by-Step Plan

1.  **Analyze `src/agents`:** Identify the files within this directory. Based on the current project state, these are likely `base.py` and `hello_world.py`.
2.  **Handle `hello_world.py`:** Move the file `src/agents/hello_world.py` to `src/specialists/hello_world.py`.
3.  **Handle `base.py`:** The file `src/agents/base.py` is a duplicate of the more up-to-date `src/specialists/base.py`. **Delete** the file `src/agents/base.py`. Do not move it.
4.  **Update Imports:** Search the entire codebase for any import statements that reference the old directory, specifically `from src.agents...`.
    *   These will likely be in `src/main.py` or `src/graph/nodes.py`.
    *   Change all occurrences to `from src.specialists...`.
5.  **Cleanup:** Delete the now-empty `src/agents` directory.

## Definition of Done
The `src/agents` directory no longer exists. All relevant code resides in `src/specialists`. The application runs successfully without any `ImportError` exceptions when executed via `python -m src.main`.
