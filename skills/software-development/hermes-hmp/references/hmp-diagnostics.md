# HMP Diagnostics — Peer Probing Workflow

Protocollo di diagnostica per verificare lo stato di un peer HMP,
dal più semplice al più approfondito.

## Tier 1: Liveness (istantaneo)

```bash
curl -s http://192.168.178.X:18643/health | jq .
```

Risposta OK tipica:
```json
{"status": "ok", "service": "hmp-gateway", "gateway_adapter": true,
 "node_id": "peer105", "bind": "0.0.0.0:18643"}
```

Cosa controlla: il plugin HMP gateway è in ascolto. NON controlla se
l'agent Hermes sottostante è vivo.

## Tier 2: Capabilities (istantaneo)

```bash
curl -s http://192.168.178.X:18643/hmp/agent-card | jq .
```

Mostra gli endpoint disponibili e il node_id. Utile per confermare
l'identità del peer e la versione del plugin.

## Tier 3: Send + Poll (10-30 secondi)

Invia un messaggio breve e poll fino a completed.

```python
import json, time, urllib.request

peer = 105  # o 84, 106, 128
msgid = f"diag_{peer}_{int(time.time()*1000000)}"
payload = json.dumps({
    "hmp_version": "1.0", "message_id": msgid,
    "idempotency_key": msgid, "from": "peer70",
    "to": f"peer{peer}", "type": "request",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "timeout": 60,
    "payload": {"text": "ping diagnostico, rispondi con OK"}
}).encode()

req = urllib.request.Request(
    f"http://192.168.178.{peer}:18643/hmp/send",
    data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=10) as r:
    result = json.loads(r.read())

print(f"Send: accepted={result.get('accepted')}, status={result.get('status')}")

if result.get("accepted"):
    time.sleep(10)
    with urllib.request.urlopen(
        f"http://192.168.178.{peer}:18643/hmp/poll/{msgid}", timeout=5) as r:
        poll = json.loads(r.read())
    print(f"Poll: status={poll.get('status')}")
    if poll.get("response_text"):
        print(f"  Risposta: {poll['response_text']}")
    if poll.get("error"):
        print(f"  Errore: {poll['error']}")
```

## Tier 4: send_and_wait (bloccante, fino a 60 secondi)

Usa l'endpoint `/hmp/send_and_wait` che fa polling lato server.

```python
data = json.dumps({
    "hmp_version": "1.0",
    "message_id": f"sw_{peer}_{int(time.time()*1000000)}",
    "idempotency_key": f"sw_{peer}_{int(time.time()*1000000)}",
    "from": "peer70", "to": f"peer{peer}", "type": "request",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "timeout": 30,
    "payload": {"text": "test send_and_wait"}
}).encode()
req = urllib.request.Request(
    f"http://192.168.178.{peer}:18643/hmp/send_and_wait",
    data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=20) as r:
    print(json.loads(r.read()))
```

## Interpretazione dei risultati

| Risultato | Significato |
|-----------|-------------|
| `/health` 200, send accepted → completed in <10s | ✅ Peer sano, plugin + agent funzionano |
| `/health` 200, send accepted → working (non diventa mai completed) | ⚠️ Plugin OK, agent bloccato. Gateway forse senza modello o in crash loop |
| `/health` 200, send accepted → completed ma risposta vuota | ⚠️ Agent ha ricevuto ma non ha prodotto risposta (o ha risposto con testo vuoto) |
| `/health` 200, send NO | ❌ Plugin in ascolto ma rifiuta il messaggio (auth, peer not allowed, empty_text) |
| `/health` connection refused | ❌ Plugin non in esecuzione. Vecchio hmp.py standalone su :8643? |
| No route to host | ❌ Peer irraggiungibile (rete, firewall, sleep) |

## Tier 5: Version verification tra peer (post-deploy)

Dopo un deploy, confrontare l'agent-card di piu peer per rilevare
deploy incompleti o bytecode obsoleto.

### 1. Confronta lunghezza risposta

```bash
# peer105 (deploy OK) — 238 byte, include version + max_text_length
curl -s http://192.168.178.105:18643/hmp/agent-card | wc -c

# peer106 (stale) — 193 byte, mancano i nuovi campi
curl -s http://192.168.178.106:18643/hmp/agent-card | wc -c
```

Se le lunghezze differiscono ma il codice sorgente e identico → **bytecode obsoleto**.

### 2. Verifica eta processo vs eta file

```bash
# Quando e partito il gateway?
ps -eo pid,lstart,cmd | grep -E '[h]ermes.*gateway'

# Quando e stato modificato il file .py?
stat -c '%y' ~/.hermes/plugins/hmp/adapter.py
```

Se il processo e partito PRIMA della modifica dei file → gateway non riavviato.
Se il processo e partito DOPO ma il bytecode e ancora vecchio → **.pyc stale** (vedi sotto).

### 3. Trova .pyc obsoleti — find e piu affidabile di ls

**Attenzione:** `ls -la __pycache__/` puo non mostrare i file (se la
directory non esiste ancora o se il glob non matcha). Usare sempre `find`:

```bash
find ~/.hermes/plugins/hmp -name '*.pyc' 2>/dev/null
find ~/.hermes/plugins/hmp -name '__pycache__' -type d
```

### 4. Ispeziona il bytecode con marshal

```bash
/usr/local/lib/hermes-agent/venv/bin/python3 -c "
import marshal
with open('/root/.hermes/plugins/hmp/__pycache__/adapter.cpython-311.pyc', 'rb') as f:
    f.read(16)
    code = marshal.load(f)
for const in code.co_consts:
    if isinstance(const, str) and 'version' in const.lower():
        print('FOUND:', repr(const))
        break
else:
    print('NOT FOUND — bytecode obsoleto')
"
```

Se il .pyc NON contiene le stringhe che il .py contiene → bytecode obsoleto.

### 5. Fix

```bash
find ~/.hermes/plugins/hmp -name '__pycache__' -type d -exec rm -rf {} \;
touch ~/.hermes/plugins/hmp/*.py
# poi riavvia il gateway
```

## Casi reali osservati (continua)

> **Nota:** Per il pattern cron di healthcheck HMP orario (pre-run script, Tirith cron-mode fallback, append-log format, persistent-state detection), vedi il reference `hmp-healthcheck-cron-pattern.md` nella skill `multi-agent-mesh`.

### peer105 (Fedora) — primo messaggio timeout, secondo OK
- **Problema:** il primo send_and_wait dopo un po' di inattività va in
  timeout (100s). Il client smette di pollare, ma il messaggio viene
  comunque processato dal peer in seguito.
- **Causa:** l'agent Hermes era in fase di cold start (caricamento
  modello, contesto, skills). Il primo messaggio faceva da "warm-up".
- **Diagnosi:** dopo il timeout, un secondo send_and_wait è andato a
  buon fine in ~4 secondi.
- **Lezione:** dopo un timeout, riprovare prima di dichiarare il peer
  morto. Il timeout è solo lato client.

### peer84 (Ubuntu) — risposte lente, messaggi complessi timeout
- **Problema:** domande multi-parte (3+ frasi) timeout a 60-120s.
  Domande semplici (yes/no) rispondono in 10-30s.
- **Causa:** hardware termicamente limitato (N56VV laptop), l'agent
  impiega molto a generare risposte complesse.
- **Workaround:** domande brevi e sequenziali, max_tokens ridotto.

### peer128 (macOS) — via broadcast irraggiungibile, via HMP diretto OK
- **Problema:** il broadcast lato client falliva con "No route to host"
  su 192.168.178.112:18643.
- **Realtà:** il plugin HMP su peer128 **rispondeva benissimo**, era
  un problema di routing specifico del client di broadcast (probabile
  ARP stale o routing table del momento).
- **Lezione:** non fidarsi del primo errore di routing. Provare
  direttamente con health check prima di escludere un peer.
