# Technical Debt Log

This document tracks known divergences from the ADRs and other technical debt items.
The goal is to acknowledge these items without blocking progress, while ensuring they are not forgotten.

## ADR-CORE-022: The Heap

| Item | Description | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **Missing `blocks` field** | `BranchPointer` lacks the `blocks` field specified in the ADR. | Cannot query "what does X block?" directly. | Additive change. Can be added later without breaking changes. |
| **Missing `tokens_consumed`** | `BranchPointer` lacks cost tracking. | No visibility into token usage per branch. | Additive change. Can be added later. |
| **Missing `schema_version`** | `ProjectManifest` lacks versioning. | Harder to migrate schema in the future. | Additive change. Default to "1.0.0" when added. |
| **Missing `load_or_create()`** | `ManifestManager` lacks this convenience method. | Minor inconvenience for consumers. | Additive change. Can be added later. |
| **Hash Chain Formula** | Implementation uses `SHA256(prev_entry.previous_hash + prev_entry.content_hash)` instead of standard Merkle pattern. | Valid and tamper-evident, but non-standard. | Accepted divergence. Ensure verification logic matches this formula. |

## General

| Item | Description | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **Test Warnings** | `datetime.utcnow()` deprecation warnings in tests. | Noise in test output. | Replace with `datetime.now(timezone.utc)` in all locations. (Partially addressed) |
