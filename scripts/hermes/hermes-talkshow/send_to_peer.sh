#!/bin/bash
# Send a message to a peer via HMP and return message_id
# Usage: send_to_peer <peer_number> <message_text> <message_id_prefix>
peer=$1
text=$2
prefix="${3:-msg}"
ts=$(date +%s)
msgid="${prefix}_${peer}_${ts}"

curl -s -X POST "http://192.168.178.${peer}:18643/hmp/send" \
  -H 'Content-Type: application/json' \
  -d "{
    \"hmp_version\": \"1.0\",
    \"message_id\": \"${msgid}\",
    \"idempotency_key\": \"${msgid}\",
    \"from\": \"peer128\",
    \"to\": \"peer${peer}\",
    \"type\": \"request\",
    \"status\": \"pending\",
    \"timestamp\": \"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\",
    \"payload\": {
        \"task_type\": \"chat\",
        \"message\": \"${text}\"
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message_id','err'))"
