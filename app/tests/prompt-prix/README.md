# LAS Test Batteries for prompt-prix

BFCL-formatted test batteries for evaluating LLM models as candidates for LAS specialists (Router, Triage, etc.)

## Quick Start

```bash
# Extract real test cases from production archives
python scripts/extract_bfcl_from_archives.py

# Output goes to: app/tests/prompt-prix/extracted/
```

## Test Files

### Extracted from Production (`./extracted/`)

Real-world test cases extracted from `./logs/archive/` execution traces.

| File | Description | Notes |
|------|-------------|-------|
| `triage_architect_bfcl.jsonl` | ContextPlan tool calls | >3K token system prompts |
| `router_specialist_bfcl.jsonl` | Route tool calls | Populated when router traces exist |

**These are the gold standard** - real prompts, real dynamically-generated system prompts, real routing decisions from production.

### Synthetic Tests (Root Directory)

Hand-crafted test cases for targeted capability evaluation.

| File | Description |
|------|-------------|
| `tool_competence_tests_bfcl.jsonl` | Basic tool calling: selection, constraints, types |
| `router_tests_bfcl.jsonl` | Router-specific: specialist selection, dependencies |

## Using with prompt-prix

1. **Copy test files to prompt-prix:**
   ```bash
   cp app/tests/prompt-prix/extracted/*.jsonl /path/to/prompt-prix/batteries/
   ```

2. **Run battery comparison:**
   - Open prompt-prix UI
   - Select battery tab
   - Load the `.jsonl` file
   - Select models to compare (e.g., `lfm2.5-instruct` vs `gpt-oss-20b`)
   - Run

## Extraction Script

`scripts/extract_bfcl_from_archives.py` converts archive traces to BFCL:

```bash
# All archives
python scripts/extract_bfcl_from_archives.py

# Last 50 archives only
python scripts/extract_bfcl_from_archives.py --limit 50

# Custom output directory
python scripts/extract_bfcl_from_archives.py --output ./my_tests/
```

## BFCL Format Reference

Each line in `.jsonl` is a test case:

```json
{
  "id": "unique_test_id",
  "question": [
    {"role": "system", "content": "...dynamic system prompt..."},
    {"role": "user", "content": "User's request"}
  ],
  "function": [{
    "name": "ContextPlan",
    "description": "...",
    "parameters": {...}
  }],
  "ground_truth": [{
    "name": "ContextPlan",
    "arguments": {
      "reasoning": "...",
      "actions": [...],
      "recommended_specialists": ["chat_specialist"]
    }
  }],
  "metadata": {
    "specialist": "triage_architect",
    "model_id": "openai/gpt-oss-20b-...",
    "timestamp": "..."
  }
}
```

## Adding More Test Data

Run LAS workflows through the UI or API - traces are automatically archived. Then re-run extraction:

```bash
# After running some workflows...
python scripts/extract_bfcl_from_archives.py
```

Deduplication is automatic - only unique (system_prompt, user_prompt) combinations are kept.
