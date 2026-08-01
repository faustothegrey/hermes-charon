#!/bin/bash
# hmp-poll - Poll un messaggio HMP fino a completamento
# Usage: hmp-poll <peer_id> <message_id> [max_attempts]
# Stampa response_text su stdout quando completed.

peer=$1
msgid=$2
max=${3:-20}  # default ~60 secondi (20 * 3s)

[ -z "$peer" ] && echo "Usage: hmp-poll <peer_id> <message_id> [max_attempts]" && exit 1
[ -z "$msgid" ] && echo "Usage: hmp-poll <peer_id> <message_id>" && exit 1

for i in $(seq 1 $max); do
  data=$(curl -s "http://192.168.178.${peer}:18643/hmp/poll/${msgid}")
  status=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)

  if [ "$status" = "completed" ]; then
    echo "$data" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('response_text','') or '(empty)')
" 2>/dev/null
    exit 0
  fi

  if [ "$status" = "failed" ]; then
    echo "$data" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"FAILED: {d.get('error','unknown')}\")
" 2>/dev/null
    exit 1
  fi

  if [ "$status" = "not_found" ]; then
    echo "ERR: message_id not found (peer ${peer}, id ${msgid})"
    exit 1
  fi

  # Still working - wait and retry
  sleep 3
done

echo "TIMEOUT: peer ${peer} did not complete after ${max} polls"
exit 1
