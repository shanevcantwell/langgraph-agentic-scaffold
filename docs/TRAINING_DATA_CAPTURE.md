# Training Data Capture for LAS

Capture real-world specialist execution data for building test datasets compatible with [prompt-prix](https://github.com/shanevcantwell/prompt-prix), BFCL, and Inspect AI.

## Overview

The `TrainingCapture` system hooks into `BaseSpecialist.execute()` to automatically capture:

| Data | Description |
|------|-------------|
| **Input Context** | Messages, scratchpad, artifacts, gathered_context |
| **Tools Available** | Function schemas available to the specialist |
| **Output** | Scratchpad, artifacts, tool calls made |
| **Outcome** | Success/failure classification with reason |
| **Metadata** | Model ID, latency, timestamps, tags |

## Quick Start

### Enable Capture

```python
from app.src.observability import TrainingCapture

# Enable at startup or runtime
TrainingCapture.enable()

# Run your workflows normally...
# All specialist executions are automatically captured

# Check capture count
print(f"Captured {TrainingCapture.count()} executions")
```

### Export to BFCL Format

```python
# Export to Berkeley Function Calling Leaderboard format (JSONL)
TrainingCapture.export_bfcl("training_data/las_captures.jsonl")
```

Output format:
```json
{"id": "las_router_specialist_000001", "question": [...], "function": [...], "ground_truth": [...], "metadata": {...}}
```

### Export to Inspect AI Format

```python
# Export to Inspect AI format (JSON)
TrainingCapture.export_inspect("training_data/las_captures_inspect.json")
```

Output format:
```json
{
  "name": "las_training_data",
  "samples": [
    {"id": "...", "input": "...", "target": {...}, "tools": [...]}
  ]
}
```

### Export Raw Data

```python
# Full capture data for analysis/debugging
TrainingCapture.export_raw("training_data/las_captures_raw.json")
```

## Outcome Classification

Executions are automatically classified:

| Outcome | Criteria |
|---------|----------|
| `success` | `task_is_complete=True` or valid routing decision |
| `failure` | Exception raised or validation failed |
| `partial` | Specialist declined or requested self-correction |
| `pending` | Unclear outcome - needs human review |

## API Reference

### Control Methods

```python
TrainingCapture.enable()           # Start capturing
TrainingCapture.disable()          # Stop capturing
TrainingCapture.is_enabled()       # Check if enabled
TrainingCapture.clear()            # Clear all captured data
TrainingCapture.count()            # Number of captures
```

### Query Methods

```python
# Get captures with filters
captures = TrainingCapture.get_captures(
    specialist="router_specialist",
    outcome=OutcomeStatus.SUCCESS,
    tags=["routing"]
)

# Get summary statistics
summary = TrainingCapture.summary()
# {'total': 42, 'by_specialist': {...}, 'by_outcome': {...}}
```

### Export Methods

```python
# Export with optional tag filter
TrainingCapture.export_bfcl("data.jsonl", filter_tags=["routing"])
TrainingCapture.export_inspect("data.json", filter_tags=["mcp"])
TrainingCapture.export_raw("data.json")
```

## Integration with prompt-prix

After exporting:

```bash
# Run BFCL format tests
prompt-prix run --format bfcl --input training_data/las_captures.jsonl

# Run Inspect AI format tests
prompt-prix run --format inspect --input training_data/las_captures_inspect.json
```

## Configuration

Enable via environment variable:

```bash
export LAS_TRAINING_CAPTURE=1
```

Or in code at startup:

```python
# In api.py or main entry point
import os
from app.src.observability import TrainingCapture

if os.getenv("LAS_TRAINING_CAPTURE"):
    TrainingCapture.enable()
```

## What Gets Captured

### For All Specialists

- Input messages (conversation history)
- Input scratchpad (transient state)
- Input artifacts (structured outputs)
- Gathered context (from Facilitator)
- Output scratchpad
- Output artifacts
- Execution latency
- Model ID (if LLM adapter present)

### For RouterSpecialist

- Routing decision made
- Alternative specialists available
- Forbidden specialists (if Menu Filter active)

### For Tool-Calling Specialists

- Tools available
- Tool calls made
- Tool choice setting

## Best Practices

1. **Run in production** to capture real user interactions
2. **Tag captures** by workflow type for targeted exports
3. **Review `pending` outcomes** to build labeled datasets
4. **Filter by specialist** when testing specific components
5. **Clear periodically** to avoid memory bloat in long-running services

## Example: Building a Router Test Suite

```python
from app.src.observability import TrainingCapture, OutcomeStatus

# After running production traffic...
router_captures = TrainingCapture.get_captures(
    specialist="router_specialist",
    outcome=OutcomeStatus.SUCCESS
)

print(f"Collected {len(router_captures)} successful routing decisions")

# Export just router data
TrainingCapture.export_bfcl(
    "router_test_suite.jsonl",
    filter_tags=["routing"]
)
```

## Files

| File | Description |
|------|-------------|
| `app/src/observability/training_capture.py` | Main capture module |
| `app/src/observability/__init__.py` | Package exports |
| `app/src/specialists/base.py` | Hook in `execute()` method |
