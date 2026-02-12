#!/usr/bin/env bash
# Reset workspace, run categorize prompt via API, extract trace from archive.
# Run from repo root: ./scripts/run_categories_test.sh
#
# Prerequisites: langgraph-app container running, LM Studio model loaded.

set -euo pipefail

API="http://localhost:8000"
PROMPT="Read the files in the categories_test folder. Based on their contents, create appropriate category subfolders and move each file into the correct category."

echo "=== Step 1: Reset categories_test ==="
docker exec langgraph-app bash -c \
  "rm -rf /workspace/categories_test/*/ && cp /workspace/categories_test_files/* /workspace/categories_test/"
echo "Files after reset:"
docker exec langgraph-app ls -1 /workspace/categories_test/

echo ""
echo "=== Step 2: Send prompt to API (synchronous invoke) ==="
echo "Prompt: $PROMPT"
echo "(waiting for completion...)"

RESPONSE=$(curl -s -X POST "$API/v1/graph/invoke" \
  -H "Content-Type: application/json" \
  -d "{\"input_prompt\": \"$PROMPT\"}")

# Save full response
echo "$RESPONSE" | python3 -m json.tool > /tmp/categories_result.json 2>/dev/null || true

echo ""
echo "=== Step 3: Results ==="

python3 -c "
import json, sys
from collections import Counter

r = json.loads('''$RESPONSE''')
fs = r.get('final_output', {})
artifacts = fs.get('artifacts', {})

# Routing
print('Routing:', fs.get('routing_history', []))
print('Task complete:', fs.get('task_is_complete'))
print()

# Resume trace
trace = artifacts.get('resume_trace', [])
print(f'Resume trace: {len(trace)} operations')
tools = Counter()
for t in trace:
    tc = t.get('tool_call', {})
    name = tc.get('name', '?')
    ok = 'ok' if t.get('success', True) else 'FAIL'
    tools[(name, ok)] += 1
for (name, ok), count in sorted(tools.items()):
    print(f'  {name}: {count} {ok}')
print()

# Knowledge base
pc = artifacts.get('project_context', {})
kb = pc.get('knowledge_base', [])
print(f'Knowledge base: {len(kb)} entries')
for entry in kb[:15]:
    print(f'  - {entry}')
print()

# EI result
ei = artifacts.get('exit_interview_result', {})
print(f'Exit Interview:')
print(f'  is_complete: {ei.get(\"is_complete\")}')
print(f'  reasoning: {ei.get(\"reasoning\", \"(none)\")[:200]}')
print(f'  missing: {ei.get(\"missing_elements\", \"(none)\")[:200]}')
print()

# Gathered context (check for retry feedback)
gc = artifacts.get('gathered_context', '')
if 'Retry Context' in gc:
    print('Gathered context: Contains EI retry feedback')
if 'Task Strategy' in gc:
    print('Gathered context: Contains task strategy reasoning')
" 2>/dev/null || echo "(parse error — see /tmp/categories_result.json)"

echo ""
echo "=== Step 4: Workspace state ==="
docker exec langgraph-app bash -c '
echo "categories_test/:"
ls -1 /workspace/categories_test/ 2>/dev/null
echo ""
for d in /workspace/categories_test/*/; do
    [ -d "$d" ] && echo "$d:" && ls -1 "$d" 2>/dev/null && echo ""
done
'

echo ""
echo "=== Step 5: Latest archive ==="
LATEST=$(ls -t logs/archive/*.zip 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    echo "Archive: $LATEST"
else
    echo "(no archives found)"
fi
echo "Full result: /tmp/categories_result.json"
