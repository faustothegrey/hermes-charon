# Lightweight HMP Peer (Pi Agent / standalone)

Un peer HMP **senza Hermes Agent** — un nodo che parla HMP ma non esegue
l'ecosistema Hermes. Utile per Raspberry Pi, dispositivi embedded, o nodi
specializzati che vogliono solo comunicare via protocollo HMP.

## Architettura

```
┌─────────────────────┐     HTTP/JSON      ┌─────────────────────┐
│  Hermes node        │    ───────────→     │  Lightweight peer   │
│  (peer70, plugin)   │    ←───────────     │  (Pi Agent)         │
│  porta :18643       │       :18643        │  porta :18643       │
└─────────────────────┘                     └─────────────────────┘
                                                 │
                                           Python stdlib only
                                           (no pip, no Hermes)
                                           Systemd managed
                                           Watchdog cron
```

## Requisiti minimi del server HMP

Un server HTTP in Python standard library (nessuna dipendenza esterna) che
espone 5 endpoint sulla porta **18643**:

| Endpoint | Metodo | Risposta |
|----------|--------|----------|
| `GET /health` | GET | `{"status": "ok", "uptime": N, "version": "1.0"}` |
| `GET /hmp/agent-card` | GET | Info peer: nome, tipo, hostname, IP, OS, hardware |
| `POST /hmp/send` | POST | Accetta messaggio, avvia processing, risponde accepted |
| `GET /hmp/poll/{message_id}` | GET | Stato corrente del messaggio |
| `POST /hmp/send_and_wait` | POST | Send + poll interno, risponde solo a processing finito |

### Messaggio standard HMP

```json
{
  "hmp_version": "1.0",
  "message_id": "msg_<timestamp>",
  "from": "peer70",
  "to": "trixie",
  "type": "request",
  "timeout": 120,
  "payload": { "text": "il messaggio" }
}
```

## Prompt template per bootstrap

Questo è il prompt da dare a un nuovo nodo perché si costruisca da solo
il server HMP. Funziona con qualsiasi agente AI sul nodo target.

Vedi `templates/prompt-bootstrap.md` per il template completo.

Struttura del prompt:

1. **Intro** — chi è il nodo, missione
2. **Spiegazione HMP** — endpoint, formato messaggio, stati
3. **Server minimale** — specifica di scrivere `hmp-server.py` con Python stdlib
4. **Test locali** — health, agent-card, send, poll, send_and_wait
5. **Systemd service** — `/etc/systemd/system/<nome>-hmp.service`
6. **Registrazione** — inviare un messaggio a peer70 (192.168.178.70:18643)
7. **Watchdog** — cron job ogni 5 minuti

## Server minimale di esempio (struttura)

```python
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json, time, threading

messages = {}  # message_id → {status, response_text, timestamp}

class HMPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_json({"status": "ok", "uptime": int(time.time()-START)})
        elif self.path == "/hmp/agent-card":
            self.send_json({...info...})
        elif self.path.startswith("/hmp/poll/"):
            msg_id = self.path.split("/")[-1]
            self.send_json(messages.get(msg_id, {"status": "not_found"}))

    def do_POST(self):
        if self.path == "/hmp/send":
            body = json.loads(self.rfile.read(...))
            msg_id = body["message_id"]
            messages[msg_id] = {"status": "accepted", ...}
            threading.Thread(target=process, args=(body,)).start()
            self.send_json({"accepted": True, "message_id": msg_id})

HTTPServer(("0.0.0.0", 18643), HMPHandler).serve_forever()
```

## Systemd unit template

```ini
[Unit]
Description=<Nome> Pi Agent - HMP Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/<user>/hmp-server.py
WorkingDirectory=/home/<user>
Restart=always
RestartSec=5
User=<user>
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Flusso di registrazione a peer70

1. Il nodo costruisce il server e lo avvia
2. Invia una richiesta POST a `http://192.168.178.70:18643/hmp/send`:

```json
{
  "hmp_version": "1.0",
  "message_id": "reg_<nome>_<timestamp>",
  "from": "<nome>",
  "to": "peer70",
  "type": "request",
  "timeout": 60,
  "payload": {
    "text": "📡 REGISTRAZIONE: <nome> online. IP: ..., OS: ..., HW: ..., Tipo: pi-agent, Porta: 18643"
  }
}
```

3. Peer70 risponde e aggiorna il proprio peer-mesh
4. Il nodo fa poll su `http://192.168.178.70:18643/hmp/poll/reg_<nome>_<timestamp>` per vedere la risposta

## Watchdog cron

```bash
#!/bin/bash
# watchdog - riavvia il server se cade
if ! curl -sf --connect-timeout 3 http://localhost:18643/health > /dev/null; then
  sudo systemctl restart <nome>-hmp.service
fi
```

Crontab (ogni 5 minuti):
```cron
*/5 * * * * /home/<user>/watchdog.sh
```

## Pitfall: il server non ha un "cervello" vero

Il server base fa solo echo del messaggio. Per renderlo utile, il processing
thread deve essere esteso per:

- Interpretare comandi specifici (es. `TEMPERATURA`, `STATO`)
- Eseguire script locali
- Rispondere con dati reali (sensori, metriche, log)
- Integrare skills specifiche del nodo

## Verifica che il peer funzioni correttamente

```bash
# Da peer70
curl -sf http://192.168.178.XXX:18643/health
curl -sf http://192.168.178.XXX:18643/hmp/agent-card

# Send + poll
MSGID="test_$(date +%s%N)"
curl -s -X POST http://192.168.178.XXX:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d "{\"hmp_version\":\"1.0\",\"message_id\":\"${MSGID}\",\"from\":\"peer70\",\"to\":\"trixie\",\"type\":\"request\",\"timeout\":120,\"payload\":{\"text\":\"Ciao!\"}}"
sleep 2
curl -s http://192.168.178.XXX:18643/hmp/poll/${MSGID}
```

## Peer registrati (rete aggiornata)

| Peer | IP | Hostname | OS | SSH User | Tipo | Note |
|------|-----|----------|-----|----------|------|------|
| peer70 | 192.168.178.70 | RPi4 | Linux | fausto | Hermes plugin | Orchestratore |
| peer84 | 192.168.178.84 | N56VV | Ubuntu | fausto | Hermes plugin | Cooling 11-17, 02-03 |
| peer105 | 192.168.178.105 | Fedora30 | Fedora | root | Hermes plugin | Lento (30-60s) |
| peer106 | 192.168.178.106 | Fedora30 | Fedora | root | Hermes plugin | Test bed |
| peer128 | 192.168.178.112 | MacBook | macOS | fausto | Hermes plugin | .112 NON .128 |
| **trixie** | **192.168.178.136** | **Trixie** | **Debian 13** | **fausto** | **Pi Agent ⭐** | **RPi 3B+, lightweight** |
| **peer138** | **192.168.178.138** | **peer138** | **RPi** | **root** | **Hermes Agent** | **Nuovo, HMP da configurare** |
