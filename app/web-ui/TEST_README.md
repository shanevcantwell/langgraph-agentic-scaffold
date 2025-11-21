# V.E.G.A.S. Terminal UI Testing

## Overview

This directory contains tests for the V.E.G.A.S. Terminal UI to prevent "vibe code problems" and ensure reliable event handling, rendering, and state management.

## Test Suite

The test suite (`public/app.test.js`) covers:

### 1. **Routing Log Tests**
- ✅ Prevents duplicate entries from `node_start` and `log` events
- ✅ Verifies correct routing order
- ✅ Validates no double-counting of specialist executions

### 2. **Thought Stream Tests**
- ✅ Validates thought stream entry metadata
- ✅ Enforces 100-entry limit to prevent memory bloat
- ✅ Tests scratchpad data extraction (triage, router, facilitator)

### 3. **Mission Report Tests**
- ✅ Parses H2 headers into dynamic tabs
- ✅ Handles markdown without headers gracefully
- ✅ Skips empty sections

### 4. **Artifact Handling Tests**
- ✅ Merges artifacts correctly without duplicates
- ✅ Skips `archive_report.md` from Artifacts tab (goes to Final Response)

### 5. **Event Type Handling Tests**
- ✅ Handles both `node_start` and `specialist_start` (backward compatibility)
- ✅ Handles both `node_end` and `specialist_end`

### 6. **Archive Data Flow Tests**
- ✅ Detects missing archive data
- ✅ Validates archive presence in workflow_end events
- ✅ Handles empty archive strings

### 7. **Integration Tests**
- ✅ Full workflow event sequence doesn't duplicate routing entries

## Running Tests

### Prerequisites

Install test dependencies:
```bash
cd app/web-ui
npm install
```

### Run All Tests
```bash
npm test
```

### Watch Mode (for development)
```bash
npm run test:watch
```

### Coverage Report
```bash
npm run test:coverage
```

## Test Output Example

```
PASS  public/app.test.js
  V.E.G.A.S. Terminal Event Handling
    Routing Log
      ✓ should not add duplicate entries from node_start and log events (3 ms)
      ✓ should add entries in correct order (1 ms)
    Thought Stream
      ✓ should add thought stream entries with correct metadata (2 ms)
      ✓ should limit thought stream to 100 entries (5 ms)
      ✓ should extract scratchpad data correctly (1 ms)
    Mission Report Rendering
      ✓ should parse H2 headers into tabs (2 ms)
      ✓ should handle markdown with no H2 headers (1 ms)
      ✓ should skip empty sections (1 ms)
    Artifact Handling
      ✓ should merge artifacts correctly (1 ms)
      ✓ should skip archive_report.md from artifacts display (1 ms)
    Event Type Handling
      ✓ should handle both node_start and specialist_start (1 ms)
      ✓ should handle both node_end and specialist_end (1 ms)
    Archive Data Flow
      ✓ should detect missing archive data (1 ms)
      ✓ should detect present archive data (1 ms)
      ✓ should handle empty archive string (1 ms)
  V.E.G.A.S. Terminal Integration
    ✓ full workflow event sequence should not duplicate routing (2 ms)

Test Suites: 1 passed, 1 total
Tests:       16 passed, 16 total
```

## Debugging Tips

### Browser Console Logging

The UI now includes debug logging for the Final Response issue. When running a workflow, check the browser console for:

```javascript
[workflow_end] Received data: {...}
[workflow_end] Archive exists: true/false
[workflow_end] Archive length: 1234
[workflow_end] Rendering mission report...
```

If you see `Archive exists: false`, the issue is in the backend (AgUiTranslator not sending archive data).
If you see `Archive exists: true` but no rendering, the issue is in the frontend (renderMissionReport function).

### Common Issues

**Issue**: Routing log shows duplicates
- **Cause**: Both `node_start` and `log` events calling `addRoutingEntry`
- **Fix**: Only call from `node_start` events (fixed in app.js:541-544)

**Issue**: Final Response tab stays empty
- **Causes**:
  1. Backend not sending `data.archive` in workflow_end event
  2. Archive string is empty
  3. renderMissionReport failing silently
- **Debug**: Check browser console for workflow_end logs

**Issue**: Artifacts tab shows archive_report.md
- **Cause**: Not filtering archive from artifacts display
- **Fix**: Filter at line 526: `if (key !== 'archive_report.md')`

## CI/CD Integration

Add to your GitHub Actions workflow:

```yaml
- name: Run UI Tests
  run: |
    cd app/web-ui
    npm install
    npm test
```

## Future Test Additions

- [ ] Neural Grid animation tests
- [ ] Theme switching tests
- [ ] File upload handling tests
- [ ] WebSocket connection stability tests
- [ ] Error state recovery tests
