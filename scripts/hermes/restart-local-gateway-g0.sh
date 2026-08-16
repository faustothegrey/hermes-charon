#!/usr/bin/env bash
set -u
echo "=== purge pycache adapter ==="
find ~/.hermes/plugins/hmp -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
echo "=== restart gateway peer70 ==="
systemctl --user restart hermes-gateway
sleep 12
systemctl --user is-active hermes-gateway
echo "--- health check ---"
curl -sf --connect-timeout 4 http://127.0.0.1:18643/health && echo
