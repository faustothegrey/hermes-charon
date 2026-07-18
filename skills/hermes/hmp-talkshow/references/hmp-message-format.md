# HMP Message Format — Talkshow Patterns

Formato del messaggio JSON da POSTare a `/hmp/send` su un peer remoto.
Porta HMP: **18643** su tutti i peer.

## Invio tema + domanda (formato breve)

```bash
ts=$(date +%s%N)
curl -s -X POST "http://192.168.178.<PEER_N>:18643/hmp/send" \
  -H "Content-Type: application/json" \
  -d '{
    "hmp_version": "1.0",
    "message_id": "r1_<PEER_N>_'${ts}'",
    "idempotency_key": "r1_<PEER_N>_'${ts}'",
    "from": "peer70",
    "to": "peer<PEER_N>",
    "type": "request",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "timeout": 120,
    "payload": {
      "text": "TEMA: ... DOMANDA: ... ⚠️ Rispondi in massimo 3-4 frasi, concreto e diretto. Se hai altro da dire lo approfondiamo dopo."
    }
  }'
```

Campi chiave:
- `message_id` / `idempotency_key`: devono essere univoci. Usare timestamp + peer_n.
- `from`: peer mittente (es. "peer70")
- `to`: peer destinatario (es. "peer105")
- `payload.text`: IL TESTO — `extract_text()` cerca `payload.text`, `payload.content`, `payload.message`, o `payload.query`. NON usare `payload.instruction`.
- `timeout`: defaults a 900s. Per talkshow va bene 120s.

## Poll per risposta

```bash
curl -s "http://192.168.178.<PEER_N>:18643/hmp/poll/<MESSAGE_ID>"
```

Risposta ha `status` = "working" | "completed" | "failed".
Se "completed", `response_text` contiene la risposta del peer.

Loop di attesa:
```bash
MSGID="..."
for i in $(seq 1 20); do
  data=$(curl -s "http://192.168.178.${PEER}:18643/hmp/poll/${MSGID}")
  status=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
  if [ "$status" = "completed" ]; then
    echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_text',''))"
    break
  fi
  if [ "$status" = "failed" ]; then
    echo "❌ fallito"
    break
  fi
  sleep 3
done
```

## Risultati osservati

Con istruzione "massimo 3-4 frasi":
- peer105: risposta in ~6 secondi (2 cicli di poll)
- peer106: risposta in ~9 secondi (3 cicli di poll)

Senza limite di lunghezza:
- peer105: risposta in 90+ secondi o mai completata

## Pattern di orchestrazione completo

```
1. PRE-SHOW: invia tema+domanda a peer105 e peer106 (unico messaggio)
2. APERTURA: tts-cast --device Pallino --voice Diego --quick "..."
3. POLL: attendi risposte da entrambi
4. LETTURA peer105: tts-cast --device Pallino --voice Elsa --quick "..."
5. LETTURA peer106: tts-cast --device Pallino --voice Isabella --quick "..."
6. FOLLOW-UP (se serve): ripeti 1-5 con nuovo messaggio
7. CHIUSURA: tts-cast --device Pallino --voice Diego --quick "..."
```

Il warm-up edge-tts (prima chiamata) può essere fatto con un breve messaggio
di test prima dello show per evitare latenza sulla prima generazione audio.
