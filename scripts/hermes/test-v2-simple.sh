#!/bin/bash
# Test server-side v2 - simple version, no set -e
echo "=== Starting server-side v2 test ==="

# Kill any existing server on :18644
kill $(lsof -t -i :18644) 2>/dev/null || true
sleep 1

# Start server in background
cd /home/fausto/.hermes/scripts
python3 -c "
import sys
sys.path.insert(0, '.')
from hmp_dual_plane import run_server
run_server(host='0.0.0.0', port=18644, node_id='peer70')
" &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"
sleep 2

# Test health
echo "=== HEALTH ==="
HEALTH=$(curl -s --connect-timeout 3 http://127.0.0.1:18644/health 2>&1)
echo "$HEALTH"

# Test send - the actual dual-plane test
echo "=== SEND ==="
SEND=$(curl -s --connect-timeout 10 -X POST http://127.0.0.1:18644/send \
  -H "Content-Type: application/json" \
  -d '{"session_id":"peer70_peer106","text":"Test server-side v2. Rispondi solo OK se funziona.","max_tokens":256}' 2>&1)
echo "$SEND"

# Clean up
sleep 3
kill $SERVER_PID 2>/dev/null || true
echo "=== DONE ==="
