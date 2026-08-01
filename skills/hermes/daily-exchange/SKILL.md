---
name: daily-exchange
description: "Daily Exchange — sistema di condivisione conoscenza tra peer Hermes. Ogni notte peer70 (Charon) richiede i digest via HMP, i peer rispondono, peer70 consolida e salva in Obsidian. v2.0.0"
type: custom
version: 2.0.0
triggers:
  - daily exchange
  - scambio conoscenza
  - digest giornaliero
  - peer58
  - sidecar
  - trixie
  - peer136
  - HMP collect
tags:
  - daily-exchange
  - HMP
  - peer-to-peer
  - knowledge-sharing
---

# Daily Exchange — v2.0.0 (HMP)

Sistema di scambio conoscenza giornaliero tra i peer della rete Hermes.
Ogni notte peer70 (Charon) invia una richiesta HMP "Daily Exchange?" a tutti i peer,
ognuno risponde col proprio digest, Charon consolida e salva nel vault Obsidian.

**Migrato da SSH+SCP a HMP send/poll il 2026-07-18.**

## Architettura (HMP)

```
03:30  Charon → HMP send a TUTTI i peer: "Daily Exchange?"
         ├── Sidecar (peer58)  → risposta HMP con digest
         ├── peer84            → risposta HMP con digest
         ├── peer105           → risposta HMP con digest
         ├── peer106           → risposta HMP con digest
         └── peer128           → risposta HMP con digest

03:35  Charon → consolida tutte le risposte
         ├── Unisce i digest in daily/YYYY-MM-DD.md
         └── Copia in Obsidian Vault Exchange/
```

**Niente più SSH, niente SCP, niente chiavi da gestire.** Tutto via HMP.

**Niente cron job no_agent.** Il collect si fa con execute_code() o script Python
che usa HMP send/poll, non più bash script con SSH.

## Peer partecipanti (rete attuale)

| Peer | ID | IP | Tipo | Partecipa | Note |
|------|-----|-----|------|-----------|------|
| **Charon** | peer70 | 192.168.178.70 | Hermes Agent | ✅ Coordinatore | Consolida e scrive in Obsidian |
| **Sidecar** | peer58 | 192.168.178.58 | Hermes Agent | ✅ Digest | Ruolo leggero, solo invio digest |
| peer84 | peer84 | 192.168.178.84 | Hermes Agent | ✅ Digest | Cooling 11-17, 02-03 |
| peer105 | peer105 | 192.168.178.105 | Hermes Agent | ✅ Digest | Lento (30-60s) |
| peer106 | peer106 | 192.168.178.106 | Hermes Agent | ✅ Digest | |
| peer128 | peer128 | 192.168.178.112 | Hermes Agent | ✅ Digest | Raggiungibile via curl (non da execute_code) |
| **trixie** | peer136 | 192.168.178.136 | Pi Agent ⭐ | ✅ Digest strutturato | pi.dev v0.80.10, metriche sistema |

### trixie (peer136) — Pi Agent, metriche sistema (v0.80.10)

trixie è un **lightweight Pi Agent** (Python stdlib, pi.dev v0.80.10).
Non ha un LLM — risponde con **dati strutturati**: metriche sistema (CPU, RAM, disco, temperatura, uptime).

**Formato digest**: risponde al prompt "Daily Exchange?" con:
```
peer: trixie
uptime: Xd Xh Xm
cpu: XX°C, load X.XX
ram: X.X/XX GB used
disk: X.X/XX GB used
notes: eventuali osservazioni scriptate
```

Incluso nella rosa di polling standard (5-10s, timeout 30s).

### Sidecar (peer58) — Ruolo

Sidecar è il **fallback** di Charon. Partecipa al Daily Exchange in
modalità leggera: invia solo il suo digest, non fa consolidamento.
Vedi `software-development/hermes-hmp` per il pattern Sidecar completo.

## Formato digest

```markdown
peer: <id>
sessioni: cosa fatto oggi
scoperte: novità imparate
problemi: bug/intoppi risolti
```

5-10 righe max. I peer confermati hanno aderito a questo formato.

## Limite messaggi HMP e Chunking

**Limite**: 2048 caratteri per messaggio HMP (imposto dal plugin v0.1.3).
Se un digest supera questo limite, si usa il **protocollo di chunking**:

```
Messaggio 1: "digest_id: <uuid> | chunk: 1/3 | <prima parte>"
Messaggio 2: "digest_id: <uuid> | chunk: 2/3 | <seconda parte>"
Messaggio 3: "digest_id: <uuid> | chunk: 3/3 | <ultima parte>"
```

Charon riceve, riassembla per `digest_id`, ordina per `chunk: N/TOT`.

## Flusso operativo

### 1. Collect (03:30)

Charon esegue (da execute_code o script Python):

```python
# Per ogni peer nella lista:
#   - HMP send: "Daily Exchange?"
#   - Poll per risposta (timeout 120s per peer)
#   - Salva risposta in ~/.hermes/exchange/<peer>/YYYY-MM-DD.md
```

Peer da contattare (con polling differenziato per latenza):

| Peer | Tempo atteso | Timeout |
|------|-------------|---------|
| peer128 | 5-10s | 60s |
| peer106 | 10-20s | 120s |
| peer58 | 10-30s | 120s |
| peer105 | 30-60s | 180s |
| peer84 | 30-60s | 180s |

poll_interval=5 secondi, max_polls adeguato al timeout.

### 2. Consolidate (03:35)

Charon unisce i file in `~/.hermes/exchange/daily/YYYY-MM-DD.md`:

```markdown
# Daily Exchange — YYYY-MM-DD

## peer70 (Charon)
- sessioni: ...
- scoperte: ...
- problemi: ...

## Sidecar (peer58)
...
```

### 3. Obsidian vault

Copia in `~/Documents/Obsidian Vault/Exchange/YYYY-MM-DD.md`.

## peer84 — Cooling schedule

peer84 è SPENTO in queste fasce:
- **11:00 → 17:00** (6h pomeriggio)
- **02:00 → 03:00** (1h notte)

L'exchange alle **03:30** cade 30 minuti dopo l'accensione delle 03:00.
È il momento ideale per contattarlo.

Se l'exchange è a un'ora che cade in cooling (es. 14:00), **saltare peer84**.

## Script

| Script | Path | Cosa fa |
|--------|------|---------|
| `daily-hmp-collect.sh` o `.py` | `~/.hermes/scripts/` | Invia richiesta HMP a tutti, raccoglie risposte, salva file |
| `daily-consolidate.sh` | `~/.hermes/scripts/` | Unisce i digest, copia in vault |

**Nota**: Gli script vecchi (`daily-collect.sh`, `daily-publish.sh`, `daily-digest.sh`)
usavano SSH+SCP e sono deprecati dalla migration HMP v2.0.0.

## Peer lenti — Pattern di polling

peer105 e peer84 impiegano 30-60s anche per messaggi semplici.
peer106 risponde in 10-20s. peer128 in 5-10s. peer58 in 10-30s.

Usare polling con timeout adeguato:

```python
import json, urllib.request, time

def poll_until_done(ip, msgid, timeout=120, interval=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        with urllib.request.urlopen(
            f"http://{ip}:18643/hmp/poll/{msgid}", timeout=5
        ) as r:
            poll = json.loads(r.read())
        status = poll.get("status")
        if status == "completed":
            return poll.get("response_text", "")
        elif status in ("failed", "timed_out"):
            return f"ERROR: {status}"
    return "TIMEOUT"
```

## Peer non raggiungibili da execute_code()

**peer128** (192.168.178.112) non è raggiungibile dal sandbox Python di
`execute_code()` — "No route to host". Usare **curl diretto** da terminal:

```bash
MSGID="dex_128_$(date +%s%N)"
curl -s -X POST http://192.168.178.112:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"'"$MSGID"'","from":"peer70","to":"peer128","type":"request","timeout":120,"payload":{"text":"Daily Exchange?"}}'

# Poll
for i in $(seq 1 20); do
  sleep 3
  resp=$(curl -s http://192.168.178.112:18643/hmp/poll/${MSGID})
  status=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
  [ "$status" = "completed" ] && echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response_text',''))" && break
  [ "$status" = "failed" ] && echo "FAIL" && break
done
```

## Cron job

I cron job vanno aggiornati da `no_agent: true` (vecchio SSH) a job con
`enabled_toolsets: ["terminal"]` (per eseguire lo script Python di collect).

| Nome | Schedule | Tipo |
|------|----------|------|
| `daily-exchange-hmp-collect` | `30 3 * * *` | Agent job (script Python con HMP) |
| `daily-exchange-consolidate` | `35 3 * * *` | `no_agent: true` (solo merge file) |

## Storico versioni

| Versione | Data | Protocollo | Note |
|----------|------|------------|------|
| v1.0.0 | 2026-07-17 | SSH+SCP | Prima implementazione, script bash |
| v1.1.0 | 2026-07-18 | SSH+SCP | peer84 cooling, Tirith workaround |
| **v2.0.0** | **2026-07-18** | **HMP send/poll** | Migrazione completa, Sidecar + trixie |
