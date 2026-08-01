#!/bin/bash
# hmp-broadcast - Invia lo stesso messaggio a tutti i peer
# Usage: hmp-broadcast <text>
# I peer si leggono da HMP_PEERS env o default: 105 106 84 128
PEERS="${HMP_PEERS:-105 106 84 128}"
text="$1"

[ -z "$text" ] && echo "Usage: hmp-broadcast <text>" && exit 1

for peer in $PEERS; do
  ts=$(date +%s%N)
  msgid="broadcast_${peer}_${ts}"

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
      \"timeout\": 60,
      \"payload\": {\"text\": \"${text}\"}
    }" 2>/dev/null)

  accepted=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accepted',False))" 2>/dev/null)
  if [ "$accepted" = "True" ]; then
    echo "✅ peer${peer}: accepted"
  else
    echo "❌ peer${peer}: $(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','?'))" 2>/dev/null)"
  fi
done
