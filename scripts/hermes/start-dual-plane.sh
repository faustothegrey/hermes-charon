#!/bin/bash
# Start the HMP Dual-Plane v2 server on port 18644
SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR"
nohup python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from hmp_dual_plane import run_server
run_server(host='0.0.0.0', port=18644, node_id='peer70')
" > /tmp/dual-plane.log 2>&1 &
echo "PID: $!"
sleep 1
curl -sf http://127.0.0.1:18644/health && echo "SERVER UP" || echo "SERVER DOWN"
