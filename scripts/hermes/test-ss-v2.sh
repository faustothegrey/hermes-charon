#!/bin/bash
echo "=== Health ==="
curl -sf http://127.0.0.1:18644/health 2>&1 || echo "HEALTH_ERR=$?"
echo ""
echo "=== Send ==="
curl -s -X POST http://127.0.0.1:18644/send \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"test_v2_check","text":"Reply OK.","max_tokens":16}' 2>&1
echo ""
