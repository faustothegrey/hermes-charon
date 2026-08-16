# REGOLA FORTE: leggere i messaggi HMP SEMPRE dal DB, MAI dal log (2026-08-16)

## Problema

Il log del gateway tronca la preview a 80 chars
(`gateway/run.py`: `_msg_preview = (event.text or "")[:80]`) e NON include
il `message_id`. Leggere il contenuto di un messaggio dal log produce FALSI
"troncamenti": messaggi che in realtà sono arrivati INTEGRI (es. 708 chars)
ma appaiono tagliati a 80. Il trasporto HMP non perde mai testo — il DB
`~/.hermes/data/hmp_gateway_plugin/messages.db` (campo `text`) è la fonte
canonica del contenuto integrale.

Caso reale (2026-08-16): peer70 invia a peer141 un messaggio di 708 chars.
Nel DB di peer141 è INTEGRO, ma il peer lo legge dal log (80 chars) e
chiede il re-invio "perché troncato". Il mittente ha già inviato tutto —
il problema è solo la fonte di lettura.

## Regola per TUTTI i peer

1. **Per leggere un messaggio ricevuto → DB, mai il log.** Helper:
   `~/.hermes/scripts/hmp-read-msg.py` (su ogni peer della rete).
2. **Se un messaggio "sembra troncato" → verificare nel DB PRIMA di
   chiedere il re-invio** al mittente (il mittente ha già inviato tutto).
3. Il log serve solo per flusso/health, non per il contenuto.
4. `message_id` NON compare nel log: per correlare usare
   `/hmp/poll/{message_id}` (risponde col testo integro dal DB) o lo
   script helper.

## Helper: hmp-read-msg.py

```bash
~/.hermes/scripts/hmp-read-msg.py <message_id>        # messaggio specifico
~/.hermes/scripts/hmp-read-msg.py --last [peer]       # ultimo (da un peer)
~/.hermes/scripts/hmp-read-msg.py --from <peer> [N]   # ultimi N da un peer
```

Output: `message_id`, from/to, status, lunghezza, TESTO INTEGRALE (+
risposta se presente). Exit 0 trovato, 1 non trovato, 2 errore db.

## Verifica rapida senza script

```bash
python3 - <<'EOF'
import sqlite3, os
db = os.path.expanduser("~/.hermes/data/hmp_gateway_plugin/messages.db")
con = sqlite3.connect(db)
row = con.execute("SELECT message_id, from_peer, status, text FROM hmp_gateway_messages ORDER BY rowid DESC LIMIT 1").fetchone()
print("id:", row[0], "| from:", row[1], "| status:", row[2], "| len:", len(row[3]))
print(row[3])
EOF
```

## Distribuzione

Lo script helper va syncato su tutti i peer (scp o rsync). Il db è lo
stesso su ogni peer (`hmp_gateway_plugin/messages.db`), quindi lo script
funziona identico ovunque.
