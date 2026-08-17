#!/usr/bin/env bash
set -u
echo "=== restart gateway peer70 (carica CAPABILITY_REUSE_COLLECTOR_PEER_ID) ==="
systemctl --user restart hermes-gateway
sleep 12
systemctl --user is-active hermes-gateway
echo "--- health ---"
curl -sf --connect-timeout 4 http://127.0.0.1:18643/health && echo
echo "--- collector nel processo ---"
tr '\0' '\n' < /proc/$(systemctl --user show hermes-gateway -p MainPID --value)/environ 2>/dev/null | grep CAPABILITY_REUSE_COLLECTOR || echo "MANCANTE"
