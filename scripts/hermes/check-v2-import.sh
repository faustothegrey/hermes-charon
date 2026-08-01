#!/bin/bash
# Simple import test + port check
echo "--- IMPORT TEST ---"
cd /home/fausto/.hermes/scripts && python3 -c "
import sys
sys.path.insert(0, '.')
from hmp_dual_plane import DualPlaneServer, SessionStore, run_server, send_to_peer
print('IMPORT OK')
print(f'Library loaded: run_server={callable(run_server)}')
print(f'send_to_peer={callable(send_to_peer)}')
" 2>&1

echo "--- PORT CHECK ---"
curl -s --max-time 2 http://127.0.0.1:18644/health 2>&1 || echo "18644: NOT LISTENING"
curl -s --max-time 2 http://127.0.0.1:18643/health 2>&1 || echo "18643: NOT LISTENING"
echo "--- DONE ---"
