#!/bin/bash
# Wait for peer response and return the response text
# Usage: wait_for_peer <peer_number> <message_id>
peer=$1
msgid=$2

while true; do
  data=$(curl -s "http://192.168.178.${peer}:18643/hmp/poll/${msgid}")
  status=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
  if [ "$status" = "completed" ]; then
    echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response_text',''))"
    break
  fi
  if [ "$status" = "failed" ]; then
    echo "[FAILED] $data" >&2
    break
  fi
  sleep 4
done
