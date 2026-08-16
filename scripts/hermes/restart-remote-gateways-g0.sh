#!/usr/bin/env bash
# Restart remoto dei gateway HMP sui peer attivi — G0 bundle deploy (16/08/2026)
# Eseguito via cron no_agent (fuori dal sandbox del gateway).
set -u

deploy_restart() {
  local U=$1 IP=$2
  echo "=== restart $IP ($U)"
  timeout 30 ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$U@$IP" "
    if [ \"$U\" = \"root\" ]; then
      systemctl restart hermes-gateway
    else
      systemctl --user restart hermes-gateway
    fi
    sleep 8
    systemctl --user is-active hermes-gateway 2>/dev/null || systemctl is-active hermes-gateway 2>/dev/null
  " 2>&1
}

deploy_restart fausto 192.168.178.141
deploy_restart root 192.168.178.138
deploy_restart fausto 192.168.178.58

echo "--- health check post-restart ---"
for ip in 141 138 58; do
  r=$(curl -sf --connect-timeout 4 "http://192.168.178.$ip:18643/health" 2>/dev/null) && echo "peer$ip: ONLINE $(echo $r | python3 -c 'import json,sys; print(json.load(sys.stdin)["node_id"])' 2>/dev/null)" || echo "peer$ip: OFFLINE"
done
