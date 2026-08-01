#!/bin/bash
echo "=== DP v2 Send Test ==="
echo "1. Health check:"
curl -sf --connect-timeout 5 http://127.0.0.1:18644/health 2>&1 && echo " - HEALTH OK" || echo " - HEALTH FAIL"
echo ""
echo "2. Send + wait for response:"
RESP=$(curl -s -X POST http://127.0.0.1:18644/send \
  -H "Content-Type: application/json" \
  -d '{"session_id":"peer70_test","text":"Rispondi solo OK se funziona.","max_tokens":64}' \
  --connect-timeout 5 --max-time 120 2>&1)
echo "$RESP"
echo ""
echo "=== END ==="
