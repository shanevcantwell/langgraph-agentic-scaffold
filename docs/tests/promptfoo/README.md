# Promptfoo Model Evaluation Tests

Model evaluation tests for Issue #88 - testing which small models correctly handle file categorization tasks.

## Purpose

These tests validate model capability for LAS specialist operations:
- **BatchProcessorSpecialist**: Structured output (JSON with file operations)
- **ProjectDirector (ReAct)**: Iterative tool calling with trace-based serialization (ADR-CORE-055)

The tests measure whether models can:
1. Parse file content semantically
2. Produce correct `move` operations (not just `read` or `list`)
3. Handle ambiguous content that references multiple categories

## Setup

```bash
# Install promptfoo globally
npm install -g promptfoo

# Or use npx
npx promptfoo eval -c docs/tests/promptfoo/file_categorization_eval.yaml
```

## Environment Variables

Configure your LM Studio endpoints:

```bash
export LMSTUDIO_RTX3090_URL="http://192.168.1.100:1234/v1"
export LMSTUDIO_RTX8000_URL="http://192.168.1.101:1234/v1"
```

Or edit the `providers` section in the YAML files directly.

## Test Files

| File | Description | Recommended |
|------|-------------|-------------|
| `file_categorization_eval.yaml` | Semantic categorization (animals/fruits/colors) | ✅ Use this |
| `file_sorting_eval.yaml` | Letter-range sorting (a-m/n-z) | Legacy |

### Why Two Test Files?

The original `file_sorting_eval.yaml` used abstract letter ranges (a-m, n-z) which confused models:
- "Sort by content" was ambiguous (filename vs content?)
- Letter ranges aren't intuitive categories
- Only 3/25 models passed correctly

The improved `file_categorization_eval.yaml` uses:
- Neutral filenames (1.txt, 2.txt) - no confounding signal
- Human-meaningful categories (animals/, fruits/, colors/)
- Semantic understanding required (not character-level tricks)

## Running Tests

```bash
# Run semantic categorization tests (recommended)
promptfoo eval -c docs/tests/promptfoo/file_categorization_eval.yaml

# Run with specific provider only
promptfoo eval -c docs/tests/promptfoo/file_categorization_eval.yaml --providers "openai:chat:qwen3-30b"

# View results in browser
promptfoo view

# Output to specific file
promptfoo eval -c docs/tests/promptfoo/file_categorization_eval.yaml -o results/categorization_results.json
```

## Adding New Models

Edit the `providers` section in the YAML:

```yaml
providers:
  - id: openai:chat:your-model
    label: "Your Model Name"
    config:
      apiHost: "http://localhost:1234"
      apiKey: "lm-studio"
      model: "your-model-name"
      temperature: 0.7
```

## Test Data Source

Test prompts and context are extracted from actual LAS workflow archives:
- `./logs/archive/run_20260130_171248_7755f43e.zip` - ProjectDirector run
- `./logs/archive/run_20260130_173705_2cf1bc22.zip` - BatchProcessor run

The `gathered_context` in tests matches what Facilitator actually provides to specialists.

Workspace test data is available for live LAS testing:
- `./workspace/categorize_test/` - 6 files (zebra, apple, blue, elephant, banana, red) + 3 folders
- `./workspace/docs_test/` - 4 markdown files (ADRs, specs, notes) + 3 folders

## Expected Behavior

For semantic categorization (`file_categorization_eval.yaml`):

| File | Content Summary | Expected Destination |
|------|-----------------|---------------------|
| `1.txt` | "The zebra is a striped animal..." | `animals/1.txt` |
| `2.txt` | "An apple is a delicious fruit..." | `fruits/2.txt` |
| `3.txt` | "The sky appears blue..." | `colors/3.txt` |
| `4.txt` | "Elephants are the largest land mammals..." | `animals/4.txt` |
| `5.txt` | "Bananas are tropical fruits..." | `fruits/5.txt` |
| `6.txt` | "Red is a primary color..." | `colors/6.txt` |

**Key assertions:**
1. Models must produce `move` operations (not just `read` or `list`)
2. Destination must include filename (e.g., `animals/1.txt`, not `animals/`)
3. Ambiguous content (e.g., "pink flamingo") should categorize by PRIMARY subject (animal, not color)

## Test Cases

| Test | Description | Files | Challenge |
|------|-------------|-------|-----------|
| Basic | 3 files, clear categories | 1-3 | Baseline semantic parsing |
| Extended | 6 files, same categories | 1-6 | Scale test |
| ADR-style | Document type classification | doc1-4.md | ADRs vs specs vs notes |
| Ambiguous | Content mentions multiple categories | a.txt, b.txt, c.txt | "golden retriever" → animal, not color |

## Results

Results are saved to `docs/tests/promptfoo/results/` with JSON output showing:
- Pass/fail per assertion
- Raw model output
- Latency metrics
- Model comparison table

## Related

- **Issue #88**: ProjectDirector loops on reads without moves
- **ADR-CORE-055**: Trace-based serialization (fixes the missing AIMessage bug)
- [TROUBLESHOOTING.md](../../dev/TROUBLESHOOTING.md) - Debugging workflow failures
