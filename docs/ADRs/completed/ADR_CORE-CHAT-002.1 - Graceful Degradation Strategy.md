# ADR: CORE-CHAT-002.1 - Graceful Degradation Strategy for Tiered Chat Subgraph

**Status:** Completed

**Prerequisite:** CORE-CHAT-002

**Context:**

CORE-CHAT-002 introduces a tiered chat subgraph with parallel execution of ProgenitorAlpha and ProgenitorBravo specialists, combined by TieredSynthesizerSpecialist. This raises several architectural questions about system behavior when components fail or are disabled:

1. **Partial Specialist Failure**: What happens if one progenitor succeeds but the other fails (LLM error, timeout, rate limit)?
2. **Configuration Disablement**: What happens if users disable one or more subgraph components in config.yaml?
3. **Backward Compatibility**: Should the system gracefully fall back to single-perspective ChatSpecialist if the tiered subgraph is unavailable?

**Decision Points:**

## Option A: Strict Requirement (Fail Fast)
- TieredSynthesizerSpecialist requires BOTH alpha_response AND bravo_response
- If either is missing, raise ValueError and route to END with error_report
- If any subgraph component is disabled, log error at startup and refuse to route to chat_specialist

**Pros:**
- Simple, predictable behavior
- Forces users to fix configuration issues
- Clear failure modes

**Cons:**
- Poor user experience when one LLM provider has transient issues
- Breaks chat functionality entirely if subgraph misconfigured
- No graceful degradation path

## Option B: Graceful Degradation (Best Effort)
- TieredSynthesizerSpecialist accepts partial responses:
  - Both present → full tiered response
  - Only one present → single-perspective response with warning
  - Neither present → raise error
- If subgraph components missing, fall back to single ChatSpecialist (if available)
- Log warnings for degraded modes

**Pros:**
- Better user experience during transient failures
- Chat functionality remains available even with misconfiguration
- Progressive enhancement mindset

**Cons:**
- More complex error handling logic
- Users might not notice degraded mode
- Inconsistent response formats (sometimes tiered, sometimes not)

## Option C: Hybrid with Circuit Breaker
- Start with strict requirement (Option A)
- Add circuit breaker pattern: if progenitors fail >3 times in 10 minutes, temporarily fall back to single ChatSpecialist
- Auto-recover when failure rate decreases
- Expose metrics via API endpoint

**Pros:**
- Best of both worlds - strict when healthy, graceful under load
- Automatic recovery from cascading failures
- Observable system health

**Cons:**
- Most complex implementation
- Requires state tracking across requests
- May need distributed coordination if scaled horizontally

**Questions to Address:**

1. What is the expected failure rate for individual LLM providers in production?
2. Should different error types (timeout vs rate limit vs LLM error) have different handling strategies?
3. Should the system expose a "health check" endpoint that reports subgraph status?
4. Should users be able to configure fallback behavior via user_settings.yaml?
5. How should the Archive Report indicate when a degraded mode was used?

**Recommendation:**

Start with **Option B (Graceful Degradation)** for Phase 1:
- Implement partial response handling in TieredSynthesizerSpecialist
- Fall back to ChatSpecialist if subgraph components missing
- Log all degraded modes with clear warnings
- Document behavior in response metadata

Upgrade to **Option C (Circuit Breaker)** in Phase 2 if production monitoring shows frequent transient failures.

**Implementation Notes:**

- Add `response_mode` to artifacts: "tiered_full", "tiered_alpha_only", "tiered_bravo_only", "single_fallback"
- Include response_mode in Archive Report for observability
- Add config option: `chat_specialist.require_all_progenitors: bool` (default: false)
- TieredSynthesizerSpecialist should use structured logging with failure reasons

**Related ADRs:**
- CORE-CHAT-002: Tiered Chat Subgraph (Fan-Out)
- CORE-CHAT-003: Diplomatic Chat Subgraph (Adversarial) - will face similar issues

**Date:** 2025-11-05
