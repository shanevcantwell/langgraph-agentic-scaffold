# Test Plan: The Heap (Phase 1)

**Date:** December 3, 2025
**Context:** Validation of ADR-CORE-022 Infrastructure
**Scope:** `app/src/specialists/schemas/_manifest.py` and `app/src/utils/manifest_manager.py`

---

## 1.0 Testing Strategy

We will employ a **Defensive Testing Strategy** focusing on failure modes, boundary conditions, and security invariants. Since this is the persistence layer for the entire agentic system, "it works on the happy path" is insufficient. We must prove "it recovers from the unhappy path."

### 1.1 Test Categories
1.  **Unit Tests (Schema):** Validate Pydantic constraints, immutability, and serialization.
2.  **Unit Tests (Manager):** Validate atomic I/O, path confinement, and CRUD operations.
3.  **Integration Tests (Forensics):** Validate hash chaining and tamper evidence.
4.  **Stress Tests (Concurrency):** Simulate race conditions (mocked) to verify locking/atomic behavior.

---

## 2.0 Test Cases

### 2.1 Schema Validation (`test_manifest_schemas.py`)

| ID | Test Case | Expected Outcome | Defensive Principle |
| :--- | :--- | :--- | :--- |
| **S-01** | **Forbid Extra Fields**<br>Attempt to initialize `BranchPointer` with an unknown field `foo="bar"`. | `ValidationError` | **Schema Strictness:** Prevent hidden data channels or typos. |
| **S-02** | **Metadata Namespacing**<br>Initialize `BranchPointer` with `metadata={"my_key": 1}` (no namespace). | `ValidationError` (or Warning) | **Namespace Hygiene:** Enforce `domain.key` pattern. |
| **S-03** | **Status Transitions**<br>Verify `BranchStatus` enum values match ADR (ACTIVE, BLOCKED, etc.). | Pass | **Contract Enforcement:** Ensure state machine validity. |
| **S-04** | **Contribution Hashing**<br>Verify `ContributionEntry` computes consistent hashes for identical content. | Pass | **Integrity:** Deterministic hashing is required for verification. |

### 2.2 Manager Logic (`test_manifest_manager.py`)

| ID | Test Case | Expected Outcome | Defensive Principle |
| :--- | :--- | :--- | :--- |
| **M-01** | **Atomic Write Survival**<br>Mock a crash (exception) *during* the `_save` write operation. | Original `manifest.json` remains untouched. | **Crash Safety:** The system must never corrupt the state file. |
| **M-02** | **Path Traversal Attack**<br>Call `add_branch(filepath="../../../etc/passwd")`. | `ValueError` / `SecurityError` | **Path Confinement:** Agents cannot escape the project root. |
| **M-03** | **Hash Chaining**<br>Log 3 contributions. Verify `entry[2].previous_hash == hash(entry[1])`. | Pass | **Tamper Evidence:** The log must form a valid blockchain. |
| **M-04** | **Tamper Detection**<br>Manually edit `manifest.json` to change an old log entry. Call `verify_integrity()`. | Return list of violations. | **Trust but Verify:** The system detects external manipulation. |
| **M-05** | **Missing Manifest Load**<br>Call `add_branch` before `load()`. | `ValueError` ("Manifest not loaded") | **State Hygiene:** Fail fast on uninitialized state. |
| **M-06** | **Duplicate Branch ID**<br>Call `add_branch` with an existing ID. | `ValueError` | **Uniqueness:** Prevent ID collisions. |

### 2.3 Concurrency & Locking (`test_manifest_concurrency.py`)

| ID | Test Case | Expected Outcome | Defensive Principle |
| :--- | :--- | :--- | :--- |
| **C-01** | **File Locking**<br>Process A holds lock. Process B attempts to acquire. | Process B waits or raises `Timeout`. | **Race Condition Prevention:** Prevent interleaved writes. |

---

## 3.0 Implementation of Tests

We will create a new test file `tests/unit/test_heap_infrastructure.py` implementing these cases using `pytest`.

### 3.1 Fixtures
*   `temp_project_dir`: A temporary directory for creating manifests.
*   `manifest_manager`: An initialized manager instance pointing to the temp dir.

### 3.2 Sample Test Code (Defensive)

```python
def test_atomic_write_failure_recovery(temp_project_dir):
    """Ensure manifest is not corrupted if save fails midway."""
    manager = ManifestManager(str(temp_project_dir / "manifest.json"))
    manager.create_project("p1", "Test", "trunk.md")
    
    original_content = (temp_project_dir / "manifest.json").read_text()
    
    # Mock open to fail halfway through writing
    with patch("builtins.open", side_effect=IOError("Disk full")):
        with pytest.raises(IOError):
            manager.add_branch("b1", "Fail", "b1.md", "snippet")
            
    # Verify original file is untouched
    assert (temp_project_dir / "manifest.json").read_text() == original_content

def test_path_traversal_prevention(temp_project_dir):
    """Ensure agents cannot write outside project root."""
    manager = ManifestManager(str(temp_project_dir / "manifest.json"))
    manager.create_project("p1", "Test", "trunk.md")
    
    with pytest.raises(ValueError, match="Path traversal detected"):
        manager.add_branch("b1", "Attack", "../../../system_file", "snippet")
```

---

## 4.0 Execution Plan

1.  **Implement Code:** `_manifest.py` and `manifest_manager.py`.
2.  **Implement Tests:** `tests/unit/test_heap_infrastructure.py`.
3.  **Run Verification:** Execute `pytest tests/unit/test_heap_infrastructure.py`.
4.  **Refine:** Fix any bugs discovered by the defensive tests.
