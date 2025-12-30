# Session Notes: 2025-12-30

## Summary

Long session covering UI fixes, model debugging, surf-mcp integration, and credential handling design.

---

## Completed Work

### 1. UI Fixes (style.css)
- Added `overscroll-behavior: contain` to prevent scroll chaining
- Added word-wrap rules to `#archiveOutput`

### 2. Model Issues Identified
- **qwen3-30b-a3b**: MoE routing failure producing degenerate "test message" output
- Filed GitHub Issue #20
- Switched Bravo to magistral-small-2509 (working)

### 3. surf-mcp Integration Fix
- **Root cause**: Container name mismatch in config.yaml
- config.yaml had `navigator-mcp`, docker-compose.yml had `surf-mcp`
- Fixed config.yaml line 76 to use `surf-mcp`
- Filed GitHub Issue #21 for integration test coverage gap

### 4. DuckDuckGo Search Investigation
- DDG library actually scrapes Bing
- Bing is in proxy allowlist, but bot detection blocks it
- Returns 200 OK with 0 results (not a 429)

---

## ADRs Created

### ADR-CORE-043: Browser Credential Handling (LAS)
**Location:** `design-docs/agentic-scaffold/03_ADRS/proposed/ADR-CORE-043_Browser_Credential_Handling.md`

**Key concepts:**
- **Browser Work Session**: User-initiated scope holding storage_state across prompts
- **Credential entry via Clarification Pattern** (ADR-CORE-042): surf-mcp signals auth needed → navigator emits ClarificationRequest → user enters creds in UI
- **Ephemeral by default**: In-memory only, clears on restart/timeout
- **Optional passphrase persistence**: Export encrypted state, passphrase lives in user's brain

**Why this matters:**
- surf-mcp is stateless by design (returns storage_state to caller)
- LAS is stateless per-prompt (no checkpointing currently)
- Without this: re-auth every single prompt
- With this: auth persists across prompts within a "work session"

---

## Key Insight from Discussion

Initial instinct was to encrypt storage_state with a locally-stored key. User correctly identified this as "security theater" - key next to lock provides no real protection.

Better model:
1. Ephemeral by default (container restart = forget)
2. If persistence needed, passphrase-derived key (key lives in user's brain)
3. Treat like ~/.ssh/ - permissions-based, not encryption-theater

---

## Pending / Not Started

1. **Test surf-mcp integration** after config fix
   - `docker-compose --profile surf up -d`
   - Verify navigator_browser_specialist connects

2. **Commit session changes**
   - config.yaml fix
   - style.css improvements
   - ADR-CORE-043

3. **GitHub Issues open:**
   - #20: qwen3-30b MoE routing failure
   - #21: surf-mcp integration tests

---

## Files Modified This Session

| File | Change |
|------|--------|
| `config.yaml` | Line 76: `navigator-mcp` → `surf-mcp` |
| `app/web-ui/public/style.css` | Scroll containment, word-wrap |
| `design-docs/.../ADR-CORE-043_Browser_Credential_Handling.md` | Created |

---

## To Resume

1. Check if surf-mcp container is running: `docker ps | grep surf`
2. If not: `docker-compose --profile surf up -d`
3. Test browser automation through Glass Cockpit
4. Commit changes when satisfied

---

*Session ended ~midnight, user signing off to kill zombies (Docker) and sleep.*
