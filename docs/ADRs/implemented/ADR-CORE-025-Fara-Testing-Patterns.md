# ADR-CORE-025: Fara Visual AI Testing Patterns

**Status:** Implemented (2026-02-18 audit). surf-mcp operational, Fara visual grounding integrated.
**Date:** 2024-12-04
**Context:** Capturing patterns from initial Fara integration for future visual AI testing

## Context

Fara-7B is a visual AI model used for UI element location and verification. During integration, several patterns emerged for:
1. LLM adapter configuration requirements
2. pytest test structure for visual AI
3. Asset management for screenshot-based tests

## Decision

### 1. LLM Adapter Requirements for Vision Models

Vision models like Fara require specific adapter configuration:

```yaml
# Minimum context window for base64 images + prompt
fara_specialist:
  model: "fara-7b"
  provider: "lmstudio"
  context_window: 4096  # Minimum 2048, recommend 4096
```

**Key considerations:**
- Base64 encoded 4K screenshots consume ~1700+ tokens
- Add buffer for prompt template (~500 tokens)
- Context pruning may be disabled for vision models (tiktoken incompatibility)

### 2. Pytest Test Structure

Three-tier testing for visual AI:

```python
# Tier 1: Mocked (no model required)
class TestVisionMocked:
    """Unit tests with mocked LLM responses."""

    @pytest.fixture
    def mocked_service(self):
        service = FaraService(adapter=mock_adapter)
        service._invoke_fara = MagicMock(return_value={"found": True, "x": 100, "y": 200})
        return service

# Tier 2: Live model (requires LM Studio)
@pytest.mark.live_llm
@pytest.mark.skipif(
    not SCREENSHOT_PATH.exists(),
    reason=f"Screenshot not found: {SCREENSHOT_PATH}"
)
class TestVisionLive:
    """Integration tests against actual vision model."""
    pass

# Tier 3: Full integration (requires UI + model)
@pytest.mark.live_llm
@pytest.mark.skipif(
    not UI_ACCESSIBLE,
    reason="Live UI not accessible"
)
class TestVisionFullIntegration:
    """End-to-end tests with live UI screenshots."""
    pass
```

### 3. Asset Management

```
app/tests/assets/
├── screenshots/
│   ├── .gitkeep
│   ├── .gitignore          # Ignore large screenshots in CI
│   └── lassi_ui.png        # LASsi UI screenshot
└── fixtures/
    └── expected_elements.json
```

**Patterns:**
- Screenshots in `.gitignore` for CI (too large)
- `.gitkeep` ensures directory exists
- Test skips gracefully when assets missing
- Document required assets in test docstrings

### 4. JiT Model Loading Pattern

For VRAM efficiency, vision models can be loaded on-demand:

```python
class FaraService:
    def __init__(self, lazy_load: bool = True):
        self._adapter = None
        self._lazy_load = lazy_load

    @property
    def adapter(self):
        if self._adapter is None and self._lazy_load:
            self._adapter = self._create_adapter()
        return self._adapter

    def unload(self):
        """Release VRAM when done with vision tasks."""
        self._adapter = None
```

### 5. Multi-Model Vision Strategy

For comprehensive UI analysis:

| Model | Purpose | Output |
|-------|---------|--------|
| Fara-7B | Element location | `{x, y, found}` coordinates |
| lfm2-vl | Scene description | Natural language description |
| Synthesis model | Critique generation | Actionable recommendations |

## Consequences

### Positive
- Clear test tiers reduce CI time (mocked tests run without GPU)
- Graceful degradation when assets/models unavailable
- JiT loading conserves VRAM for multi-model workflows

### Negative
- Live tests require local LM Studio setup
- Large screenshots excluded from git (must be added locally)
- Context window requirements not enforced at config validation time

## Future Work

1. **Config validation**: Warn if vision model context_window < 2048
2. **CI integration**: Consider cloud vision API fallback for CI
3. **Asset management**: Explore LFS or artifact storage for screenshots
4. **Prompt optimization**: Via prompt-prix for vision prompts
