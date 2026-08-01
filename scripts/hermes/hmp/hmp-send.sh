#!/bin/bash
# hmp-send - Invia un messaggio HMP a un peer e stampa il message_id
# Usage: hmp-send <peer_id> <text> [message_id_prefix]
# Esempio: hmp-send 105 "Ciao!" ping_105

peer=$1
text=$2
prefix="${3:-msg}"
[ -z "$peer" ] && echo "Usage: hmp-send <peer_id> <text> [prefix]" && exit 1
[ -z "$text" ] && echo "ERR: text required" && exit 1

ts=$(date +%s%N)
msgid="${prefix}_${peer}_${ts}"

curl -s -X POST "http://192.168.178.${peer}:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d "{
    \"hmp_version\": \"1.0\",
    \"message_id\": \"${msgid}\",
    \"idempotency_key\": \"${msgid}\",
    \"from\": \"peer70\",
    \"to\": \"peer${peer}\",
    \"type\": \"request\",
    \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"timeout\": 120,
    \"payload\": {\"text\": \"${text}\"}
  }" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('message_id','ERR'))
if not d.get('accepted'):
    print(f'ERR: {d.get(\"error\",\"unknown\")}', file=sys.stderr)
    exit(1)
" 2>&1
