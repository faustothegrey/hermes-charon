#!/bin/bash
SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR"
curl -s -X POST http://127.0.0.1:18644/send \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"peer70_peer106","text":"Test server-side v2. Rispondi solo OK se funziona.","max_tokens":256}'
echo ""
