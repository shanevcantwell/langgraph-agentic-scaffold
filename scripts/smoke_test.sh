#!/usr/bin/env bash
# scripts/smoke_test.sh — Stopgap smoke tests for LAS (#269)
#
# Curl-based regression tests against the running container.
# No pytest dependency. Two tiers:
#   ./scripts/smoke_test.sh          Tier 1 (quick, ~1-2 min)
#   ./scripts/smoke_test.sh --full   Tier 1 + Tier 2 (~10-15 min)
#
# Exit codes: 0 = all pass, 1 = failures, 2 = container unreachable

set -euo pipefail

BASE_URL="${LAS_BASE_URL:-http://localhost:8000}"
QUICK_TIMEOUT=300   # seconds per quick test (local models can be slow)
FULL_TIMEOUT=900    # seconds per full-pipeline test

# --- Counters ---
PASS=0
FAIL=0
SKIP=0
TOTAL_START=$(date +%s)

# --- Helpers ---

red()    { printf '\033[0;31m%s\033[0m' "$*"; }
green()  { printf '\033[0;32m%s\033[0m' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m' "$*"; }
bold()   { printf '\033[1m%s\033[0m' "$*"; }

# Error indicators borrowed from conftest.py
ERROR_PATTERNS='catastrophic|Workflow failed|CRITICAL ERROR|Internal Server Error'

report() {
    local status="$1" name="$2" elapsed="$3" detail="${4:-}"
    case "$status" in
        PASS) printf " [%s] %-40s %s\n" "$(green PASS)" "$name" "${elapsed}s" ;;
        FAIL) printf " [%s] %-40s %s  %s\n" "$(red FAIL)" "$name" "${elapsed}s" "$detail";;
        SKIP) printf " [%s] %-40s %s\n" "$(yellow SKIP)" "$name" "$detail" ;;
    esac
}

pass() { PASS=$((PASS + 1)); report PASS "$1" "$2"; }
fail() { FAIL=$((FAIL + 1)); report FAIL "$1" "$2" "$3"; }
skip() { SKIP=$((SKIP + 1)); report SKIP "$1" "$2"; }

elapsed_since() { echo $(( $(date +%s) - $1 )); }

check_no_errors() {
    local body="$1"
    if echo "$body" | grep -qiE "$ERROR_PATTERNS"; then
        return 1
    fi
    return 0
}

# --- Tests ---

test_health() {
    local start=$(date +%s)
    local resp
    resp=$(curl -s --max-time 10 "$BASE_URL/" 2>/dev/null) || { fail "Health check" "$(elapsed_since $start)" "Connection refused"; return; }

    if echo "$resp" | grep -q '"status"'; then
        pass "Health check" "$(elapsed_since $start)"
    else
        fail "Health check" "$(elapsed_since $start)" "Unexpected response"
    fi
}

test_models() {
    local start=$(date +%s)
    local resp
    resp=$(curl -s --max-time 10 "$BASE_URL/v1/models" 2>/dev/null) || { fail "Models endpoint" "$(elapsed_since $start)" "Request failed"; return; }

    if echo "$resp" | jq -e '.data[] | select(.id == "las-default")' >/dev/null 2>&1; then
        pass "Models endpoint" "$(elapsed_since $start)"
    else
        fail "Models endpoint" "$(elapsed_since $start)" "las-default not found"
    fi
}

test_ping_sync() {
    local start=$(date +%s)
    local resp
    resp=$(curl -s --max-time "$QUICK_TIMEOUT" "$BASE_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"las-simple","stream":false,"messages":[{"role":"user","content":"What is 2+2? Answer in one sentence."}]}' \
        2>/dev/null) || { fail "Ping (sync, simple)" "$(elapsed_since $start)" "Request failed/timeout"; return; }

    local content
    content=$(echo "$resp" | jq -r '.choices[0].message.content // empty' 2>/dev/null)

    if [ -z "$content" ]; then
        fail "Ping (sync, simple)" "$(elapsed_since $start)" "No content in response"
        return
    fi

    if [ ${#content} -lt 5 ]; then
        fail "Ping (sync, simple)" "$(elapsed_since $start)" "Content too short: ${content}"
        return
    fi

    if ! check_no_errors "$content"; then
        fail "Ping (sync, simple)" "$(elapsed_since $start)" "Error in response"
        return
    fi

    pass "Ping (sync, simple)" "$(elapsed_since $start)"
}

test_tiered_chat_stream() {
    local start=$(date +%s)
    local tmpfile
    tmpfile=$(mktemp)
    trap "rm -f $tmpfile" RETURN

    local http_code
    http_code=$(curl -s --max-time "$QUICK_TIMEOUT" -o "$tmpfile" -w '%{http_code}' \
        "$BASE_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"las-default","stream":true,"messages":[{"role":"user","content":"What is the capital of France? Answer briefly."}]}' \
        2>/dev/null) || { fail "Tiered chat (stream)" "$(elapsed_since $start)" "Request failed/timeout"; return; }

    if [ "$http_code" != "200" ]; then
        fail "Tiered chat (stream)" "$(elapsed_since $start)" "HTTP $http_code"
        return
    fi

    local has_done=false has_reasoning=false has_content=false

    while IFS= read -r line; do
        case "$line" in
            "data: [DONE]") has_done=true ;;
            data:\ *)
                local payload="${line#data: }"
                # Check for reasoning_content
                if echo "$payload" | jq -e '.choices[0].delta.reasoning_content // empty | select(. != "")' >/dev/null 2>&1; then
                    has_reasoning=true
                fi
                # Check for content
                if echo "$payload" | jq -e '.choices[0].delta.content // empty | select(. != "")' >/dev/null 2>&1; then
                    has_content=true
                fi
                ;;
        esac
    done < "$tmpfile"

    local failures=""
    if ! $has_done; then failures="no [DONE]; "; fi
    if ! $has_content; then failures="${failures}no content delta; "; fi
    # reasoning_content is expected but not strictly required
    if ! $has_reasoning; then failures="${failures}(no reasoning_content); "; fi

    if [ -n "$failures" ] && echo "$failures" | grep -qv '^('; then
        fail "Tiered chat (stream)" "$(elapsed_since $start)" "$failures"
    else
        pass "Tiered chat (stream)" "$(elapsed_since $start)"
    fi
}

test_research_stream() {
    local start=$(date +%s)
    local tmpfile
    tmpfile=$(mktemp)
    trap "rm -f $tmpfile" RETURN

    local http_code
    http_code=$(curl -s --max-time "$FULL_TIMEOUT" -o "$tmpfile" -w '%{http_code}' \
        "$BASE_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"las-default","stream":true,"messages":[{"role":"user","content":"Search the web for the current population of Tokyo and summarize what you find in 2-3 sentences."}]}' \
        2>/dev/null) || { fail "Research query (stream)" "$(elapsed_since $start)" "Request failed/timeout"; return; }

    if [ "$http_code" != "200" ]; then
        fail "Research query (stream)" "$(elapsed_since $start)" "HTTP $http_code"
        return
    fi

    local has_done=false has_content=false
    while IFS= read -r line; do
        case "$line" in
            "data: [DONE]") has_done=true ;;
            data:\ *)
                local payload="${line#data: }"
                if echo "$payload" | jq -e '.choices[0].delta.content // empty | select(. != "")' >/dev/null 2>&1; then
                    has_content=true
                fi
                ;;
        esac
    done < "$tmpfile"

    if $has_done && $has_content; then
        pass "Research query (stream)" "$(elapsed_since $start)"
    else
        local failures=""
        if ! $has_done; then failures="no [DONE]; "; fi
        if ! $has_content; then failures="${failures}no content; "; fi
        fail "Research query (stream)" "$(elapsed_since $start)" "$failures"
    fi
}

test_file_operation_stream() {
    local start=$(date +%s)
    local tmpfile
    tmpfile=$(mktemp)
    trap "rm -f $tmpfile" RETURN

    local http_code
    http_code=$(curl -s --max-time "$FULL_TIMEOUT" -o "$tmpfile" -w '%{http_code}' \
        "$BASE_URL/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"las-default","stream":true,"messages":[{"role":"user","content":"List the files in the /workspace directory and briefly describe what you find."}]}' \
        2>/dev/null) || { fail "File operation (stream)" "$(elapsed_since $start)" "Request failed/timeout"; return; }

    if [ "$http_code" != "200" ]; then
        fail "File operation (stream)" "$(elapsed_since $start)" "HTTP $http_code"
        return
    fi

    local has_done=false has_content=false
    while IFS= read -r line; do
        case "$line" in
            "data: [DONE]") has_done=true ;;
            data:\ *)
                local payload="${line#data: }"
                if echo "$payload" | jq -e '.choices[0].delta.content // empty | select(. != "")' >/dev/null 2>&1; then
                    has_content=true
                fi
                ;;
        esac
    done < "$tmpfile"

    if $has_done && $has_content; then
        pass "File operation (stream)" "$(elapsed_since $start)"
    else
        local failures=""
        if ! $has_done; then failures="no [DONE]; "; fi
        if ! $has_content; then failures="${failures}no content; "; fi
        fail "File operation (stream)" "$(elapsed_since $start)" "$failures"
    fi
}

test_headless_discovery() {
    local start=$(date +%s)
    local resp
    resp=$(curl -s --max-time 10 "$BASE_URL/v1/runs/active" 2>/dev/null) || { fail "Headless discovery" "$(elapsed_since $start)" "Request failed"; return; }

    if echo "$resp" | jq -e '.runs' >/dev/null 2>&1; then
        pass "Headless discovery" "$(elapsed_since $start)"
    else
        fail "Headless discovery" "$(elapsed_since $start)" "Invalid response structure"
    fi
}

# --- Main ---

usage() {
    echo "Usage: $0 [--full] [--help]"
    echo ""
    echo "  (no args)   Tier 1: health, models, ping, tiered chat (~1-2 min)"
    echo "  --full      Tier 1 + Tier 2: + research, file ops, headless (~10-15 min)"
    echo "  --help      This message"
    exit 0
}

FULL=false
for arg in "$@"; do
    case "$arg" in
        --full) FULL=true ;;
        --help|-h) usage ;;
        *) echo "Unknown arg: $arg"; usage ;;
    esac
done

echo ""
bold "LAS Smoke Tests"
echo " Target: $BASE_URL"
echo ""

# Pre-flight: is the container up?
if ! curl -s --max-time 5 "$BASE_URL/" >/dev/null 2>&1; then
    echo " $(yellow "[SKIP]") Container unreachable at $BASE_URL"
    echo ""
    echo " Container is down or API not ready. Start with:"
    echo "   docker compose up -d"
    echo ""
    exit 2
fi

echo "$(bold "Tier 1 — Quick")"
test_health
test_models
test_ping_sync
test_tiered_chat_stream

if $FULL; then
    echo ""
    echo "$(bold "Tier 2 — Full Pipeline")"
    test_research_stream
    test_file_operation_stream
    test_headless_discovery
fi

# --- Summary ---
TOTAL=$((PASS + FAIL))
ELAPSED=$(elapsed_since $TOTAL_START)
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo " $(green "$PASS/$TOTAL passed") (${ELAPSED}s)"
else
    echo " $(red "$PASS/$TOTAL passed, $FAIL FAILED") (${ELAPSED}s)"
fi

if [ "$SKIP" -gt 0 ]; then
    echo " ($SKIP skipped)"
fi

echo ""
exit $( [ "$FAIL" -eq 0 ] && echo 0 || echo 1 )
