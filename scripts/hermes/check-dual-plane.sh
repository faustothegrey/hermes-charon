#!/bin/bash
echo "=== Checking :18644 ==="
curl -sf --connect-timeout 3 http://127.0.0.1:18644/health && echo "SERVER UP" || echo "SERVER DOWN"
echo "=== Checking :18643 ==="
curl -sf --connect-timeout 3 http://127.0.0.1:18643/health && echo "HMP UP" || echo "HMP DOWN"
echo "=== Checking :8642 ==="
curl -sf --connect-timeout 3 http://127.0.0.1:8642/health 2>&1 && echo "API UP" || echo "API DOWN"
echo "=== Done ==="
