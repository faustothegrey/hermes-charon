#!/usr/bin/env bash
# Collect unread Libero emails for the LLM watchdog job.
# Outputs compact JSON of unread envelopes + full text of each.
# Empty output = no unread emails (job should stay silent).
set -u

UNREAD=$(himalaya envelope list -a libero --output json "not flag seen" 2>/dev/null)
if [ -z "$UNREAD" ] || [ "$UNREAD" = "[]" ]; then
  exit 0
fi

COUNT=$(echo "$UNREAD" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
echo "UNREAD_COUNT=$COUNT"

# Envelope metadata
echo "$UNREAD" | python3 -c "
import json, sys
for e in json.load(sys.stdin):
    print(f\"ID={e['id']} | SUBJECT={e.get('subject','(no subject)')} | FROM={e.get('from',{}).get('addr','?')} | DATE={e.get('date','')} | ATTACH={'yes' if e.get('has_attachment') else 'no'}\")
"

echo "---FULL TEXT---"
for ID in $(echo "$UNREAD" | python3 -c "import json,sys; print(' '.join(str(e['id']) for e in json.load(sys.stdin)))" 2>/dev/null); do
  echo "=== EMAIL ID $ID ==="
  himalaya message read -a libero --preview "$ID" 2>/dev/null
  echo
done
