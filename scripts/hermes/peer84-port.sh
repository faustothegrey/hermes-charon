#!/usr/bin/env bash
# peer84-port.sh — Apre/chiude/controlla le porte su peer84 via API Hermes
# peer70 (orchestratore 24/7) -> peer84 (N56VV) API call
#
# Uso:
#   peer84-port.sh open       # apre porte 2222+3001 ("apriti sedano")
#   peer84-port.sh close      # chiude porte ("chiudi sedano")
#   peer84-port.sh status     # mostra stato porte
#   peer84-port.sh keepalive  # prolunga apertura di 20 min ("Sisisi")
#

PEER84_HOST="192.168.178.84"
PEER84_PORT="8642"
PEER84_KEY="6j-h7Q5pR70Y2OXPVwtn-Mlv5DZItxu8d_tbwUYPD5uo5rf6G5E5aqQKdraydn2a"

case "${1:-}" in
  open)
    MSG="apriti sedano"
    ;;
  close)
    MSG="chiudi sedano"
    ;;
  status)
    MSG="che stato hanno le porte?"
    ;;
  keepalive)
    MSG="Sisisi"
    ;;
  *)
    echo "Uso: $0 {open|close|status|keepalive}"
    echo ""
    echo "  open       — apre porte 2222 (SSH) e 3001 (API) per 20 min"
    echo "  close      — chiude le porte immediatamente"
    echo "  status     — mostra lo stato attuale"
    echo "  keepalive  — prolunga apertura di altri 20 min"
    exit 1
    ;;
esac

PAYLOAD=$(cat <<EOF
{
  "model": "hermes-agent",
  "messages": [{"role": "user", "content": "$MSG"}],
  "max_tokens": 200
}
EOF
)

RESP=$(curl -s --max-time 90 \
  -X POST "http://${PEER84_HOST}:${PEER84_PORT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${PEER84_KEY}" \
  -d "$PAYLOAD" 2>&1)

echo "$RESP" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    msg = data['choices'][0]['message']['content']
    print(msg)
except Exception as e:
    print(f'ERRORE: {e}')
    print('(raw response above)')
    sys.exit(1)
"
