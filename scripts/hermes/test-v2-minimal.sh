#!/bin/bash
# Minimal server-side v2 test - no set -e, no lsof dependency
echo "=== V2 TEST START ==="

# Try to start server on :18644 (will fail if port taken, that's OK)
cd /home/fausto/.hermes/scripts
python3 -c "
import sys, os, socket
sys.path.insert(0, '.')
from hmp_dual_plane import run_server
try:
    s = socket.socket()
    s.settimeout(1)
    s.bind(('0.0.0.0', 18644))
    s.close()
    os.environ['HMP_NODE_ID'] = 'peer70'
    run_server(host='0.0.0.0', port=18644, node_id='peer70')
except OSError:
    print('PORT 18644 ALREADY IN USE')
except Exception as e:
    print(f'SERVER ERROR: {e}')
" &
SPID=$!
sleep 3

# Health check
echo "--- HEALTH ---"
curl -s --max-time 3 http://127.0.0.1:18644/health 2>&1 || echo "HEALTH_FAILED"

# Send test
echo "--- SEND ---"
curl -s --max-time 30 -X POST http://127.0.0.1:18644/send \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test_v2_peer70","text":"Test server-side v2. Rispondi solo OK se funziona.","max_tokens":64}' 2>&1 || echo "SEND_FAILED"

# Cleanup
kill $SPID 2>/dev/null
sleep 1
echo "=== V2 TEST END ==="
