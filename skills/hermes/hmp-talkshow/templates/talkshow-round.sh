#!/bin/bash
# talkshow-round.sh — Esegue un round completo del talkshow
# Uso: ./talkshow-round.sh <peer_n> <voce_guest> "<domanda>" "<contenuto_risposta>"
# Esempio: ./talkshow-round.sh 105 Elsa "Cosa vedere?" "Peer105 dice: il castello..."
#
# Prerequisiti:
#   - Cache tts-cast già popolata (prima chiamata senza --quick già eseguita)
#   - edge-tts installato
#   - PEER_N, DOMANDA, RISPOSTA passati come argomenti

PEER="${1:?Manca peer_n (es. 105)}"
VOCE="${2:?Manca voce (es. Elsa)}"
DOMANDA="${3:?Manca domanda}"
RISPOSTA="${4:?Manca testo risposta}"

TS=$(date +%s%N)
MSGID="r_${PEER}_${TS}"

echo "🎙️ Round peer${PEER} — ${VOCE}"

# 1. Conduttore: dice la domanda su Pallino (Diego, quick)
echo "  🎤 Conduttore: $DOMANDA"
python3 ~/.hermes/scripts/tts-cast.py --device Pallino --voice it-IT-DiegoNeural --quick \
  "$DOMANDA" 2>&1 | grep -E "✅|⚡|PLAYING"

# 2. Invia domanda al peer via HMP
echo "  📡 Invio a peer${PEER}..."
curl -s -X POST "http://192.168.178.${PEER}:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d "{
    \"hmp_version\": \"1.0\",
    \"message_id\": \"${MSGID}\",
    \"idempotency_key\": \"${MSGID}\",
    \"from\": \"peer70\",
    \"to\": \"peer${PEER}\",
    \"type\": \"request\",
    \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"timeout\": 120,
    \"payload\": {
      \"text\": \"${DOMANDA} ⚠️ Rispondi in massimo 3-4 frasi, concreto e diretto.\"
    }
  }" > /dev/null 2>&1

# 3. Poll per risposta
echo "  ⏳ Attesa risposta..."
for i in $(seq 1 20); do
  data=$(curl -s "http://192.168.178.${PEER}:18643/hmp/poll/${MSGID}")
  status=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  if [ "$status" = "completed" ]; then
    R=$(echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_text',''))" 2>/dev/null)
    echo "  ✅ peer${PEER}: pronto"
    # Se non è stata passata una risposta predefinita, usa quella dal peer
    if [ -z "$RISPOSTA" ]; then
      echo "  📝 Risposta ricevuta (${#R} chars)"
    fi
    break
  fi
  if [ "$status" = "failed" ]; then echo "  ❌ peer${PEER} fallito"; break; fi
  sleep 3
done

# 4. Leggi risposta su Pallino
echo "  🎤 Lettura risposta..."
python3 ~/.hermes/scripts/tts-cast.py --device Pallino --voice "it-IT-${VOCE}Neural" --quick \
  "${RISPOSTA}" 2>&1 | grep -E "✅|⚡|PLAYING"

echo "  ✅ Round peer${PEER} completato"
