# PROPOSAL: Finalize Configuration-Driven Adapter Architecture

*   **Status:** Applied
*   **Author:** Senior Systems Architect
*   **Date:** 2025-08-18 2:10AM

## 1. Executive Summary

This proposal outlines the final refactoring steps to fully implement the configuration-driven Adapter architecture. The current codebase contains obsolete references to a deprecated `LLMClientFactory` and an incorrect `BaseSpecialist` contract. This work will align all core components—the `BaseSpecialist` abstraction, all concrete specialists, and the `ChiefOfStaff` orchestrator—with the new, superior architecture defined in `config.yaml`. This will resolve all broken references and establish a stable, scalable, and maintainable foundation.

## 2. Problem Statement

The recent architectural shift to a decoupled, configuration-driven model has left several core components in an inconsistent and non-functional state:
1.  The `BaseSpecialist` `__init__` method has an obsolete signature, causing `TypeError` exceptions on instantiation.
2.  Concrete specialists are attempting to call a non-existent `self.llm_client.invoke()` method. The correct method is now `self.llm_adapter.invoke()`.
3.  The `ChiefOfStaff` is attempting to instantiate specialists using an outdated pattern.
4.  The `DEVELOPERS_GUIDE.md` is dangerously out of sync with the new architecture, providing incorrect instructions and code templates.

## 3. Proposed Solution

A system-wide refactoring will be performed to bring all components into compliance with the new architecture. The `BaseSpecialist` will be updated to be initialized by `specialist_name`, using the `ConfigLoader` and `AdapterFactory` to self-configure. All concrete specialists will be updated to conform to this new contract. The `ChiefOfStaff` will be simplified to instantiate specialists by name. Finally, the `DEVELOPERS_GUIDE.md` will be completely rewritten to reflect the new reality.

## 4. Impact Analysis

*   **Benefits:** This change will fix all known instantiation and invocation errors, creating a functional system. It will fully realize the benefits of the new architecture: complete decoupling, enhanced scalability, and simplified specialist development.
*   **Risks:** This is a significant internal refactoring. The risk is mitigated by the fact that the target state is well-defined and all changes are coordinated.

## 5. Manifest Reference

All file modifications required to execute this proposal are detailed in `MANIFEST.json`.