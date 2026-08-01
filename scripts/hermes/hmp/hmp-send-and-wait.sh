#!/bin/bash
# hmp-send-and-wait - Invia messaggio HMP e aspetta la risposta
# Usage: hmp-send-and-wait <peer_id> <text> [message_id_prefix]
# 
# Combina send + poll in un unico comando. Output: response_text
# Esempio:
#   R=$(hmp-send-and-wait 105 "Ciao?" domanda)
#   echo "$R"
# 
# Per debug: HMP_DEBUG=1 hmp-send-and-wait 105 "test"

peer=$1
text=$2
prefix="${3:-msg}"

[ -z "$peer" ] && echo "Usage: hmp-send-and-wait <peer_id> <text> [prefix]" && exit 1
[ -z "$text" ] && echo "ERR: text required" && exit 1

# Send
ts=$(date +%s%N)
msgid="${prefix}_${peer}_${ts}"

resp=$(curl -s -X POST "http://192.168.178.${peer}:18643/hmp/send" \
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
  }" 2>/dev/null)

accepted=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accepted',False))" 2>/dev/null)
[ "$accepted" != "True" ] && echo "ERR: not accepted - $resp" && exit 1

[ -n "$HMP_DEBUG" ] && echo "  → sent: $msgid" >&2

# Poll
for i in $(seq 1 30); do
  data=$(curl -s "http://192.168.178.${peer}:18643/hmp/poll/${msgid}" 2>/dev/null)
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
    echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'FAILED: {d.get(\"error\",\"unknown\")}')" 2>/dev/null
    exit 1
  fi
  if [ "$status" = "not_found" ]; then
    echo "ERR: message_id not found"
    exit 1
  fi
  sleep 3
done

echo "TIMEOUT after 90s"
exit 1
