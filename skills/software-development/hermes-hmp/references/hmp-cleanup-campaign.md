# HMP Standalone Cleanup Campaign — 2026-07-16

Risultato della campagna di cleanup del vecchio server hmp.py standalone
(porta 8643) su tutti i peer della rete, in favore del plugin HMP gateway
(porta 18643).

## Procedura

1. **Sondaggio** — broadcast a tutti i peer: "Sei pronto a ritirare il
   vecchio hmp standalone? SI o NO."
2. **Diagnostica** — health check su :8643 e :18643 per ogni peer.
3. **Cleanup** — incaricato il peer di rimuovere i propri residui.
4. **Verifica indipendente** — controllato :8643 morto, :18643 vivo,
   send+poll funzionante.

## Risultati peer per peer

### peer105 (192.168.178.105 — Fedora 30 aarch64)

| Controllo | Risultato |
|-----------|-----------|
| Vecchio hmp.py su :8643 | ❌ Connection refused — già fermo |
| Plugin HMP su :18643 | ✅ Attivo, node_id=peer105 |
| Risposta al sondaggio | Timeout (100s) — primo messaggio dopo inattività |
| Risposta a ping successivo | ✅ "OK" in ~4s |
| Cleanup delegato | Risultato: **NIENTE** — nessun file residuo, nessun servizio, nessun cron |

**Note:** peer105 è lento al primo messaggio (cold start dell'agent, ~40s).
Un secondo messaggio subito dopo va in ~4s. Hardware Fedora 30 che impiega
a caricare il modello?

### peer106 (192.168.178.106 — Fedora 30 aarch64)

| Controllo | Risultato |
|-----------|-----------|
| Vecchio hmp.py su :8643 | ❌ Connection refused — già fermo |
| Plugin HMP su :18643 | ✅ Attivo, node_id=peer106 |
| Risposta al sondaggio | ✅ "SI" |
| Cleanup delegato | Completato in ~170s |

**Cosa rimosso:**
- Servizi systemd: `hmp-server.service`, `hmp-worker.service`
- File standalone: `/usr/local/bin/hmp.py`, `/usr/local/bin/watchdog_hmp.py`
- Pycache: `/usr/local/bin/__pycache__/hmp.cpython-37.pyc`
- POC: `/root/hmp_gateway_plugin_poc.py`
- File systemd: `/etc/systemd/system/hmp-server.service`, `/etc/systemd/system/hmp-worker.service`
- Cron: watchdog ogni 30 minuti come root

**Verifica indipendente:**
- ✅ :8643 → Connection refused
- ✅ :18643 → gateway_adapter=true, node_id=peer106
- ✅ Send+poll → "OK" in ~4s

### peer84 (192.168.178.84 — Ubuntu N56VV)

| Controllo | Risultato |
|-----------|-----------|
| Vecchio hmp.py su :8643 | ❌ Connection refused — già fermo |
| Plugin HMP su :18643 | ✅ Attivo, node_id=peer84 |
| Gateway API su :8642 | ✅ Attivo (v0.16.0) |
| Risposta al sondaggio | **"NO"** |
| Risposta a domanda successiva | "NO" — il vecchio hmp.py non è attivo |

**Verifica SSH (root@192.168.178.84):**

| Cosa | Risultato |
|------|-----------|
| `/usr/local/bin/hmp.py` | ⚠️ **Ancora presente** (43273 byte) |
| `/usr/local/bin/worker_llm.py` | ⚠️ **Ancora presente** (2394 byte) |
| `watchdog_hmp.py` | ✅ Assente |
| `/etc/systemd/system/hmp-server.service` | ⚠️ **Ancora presente** |
| `/etc/systemd/system/hmp-worker.service` | ⚠️ **Ancora presente** |
| Cron job hmp | ✅ Nessuno |
| Porta 8643 | ✅ Non in ascolto |
| Porta 18643 | ✅ Plugin HMP attivo |

**Interpretazione:** ecco perché peer84 ha detto NO — aveva ancora file
e servizi systemd installati, anche se il server su :8643 non girava.
Le risposte "NO" erano corrette da parte sua.

**Azione:** da eseguire cleanup — rimozione file e servizi systemd
tramite SSH o delegando il peer.

### peer128 (192.168.178.112 — macOS)

| Controllo | Risultato |
|-----------|-----------|
| Broadcast via script | ❌ "No route to host" |
| Health check diretto su :18643 | ✅ Risponde (gateway_adapter=true, node_id=peer128) |
| Vecchio hmp.py su :8643 | ❌ Connection refused — già fermo |
| Gateway API su :8642 | ✅ Attivo |

**Interpretazione:** il plugin HMP su peer128 è attivo e funzionante.
Il fallimento del broadcast era un falso negativo di routing (ARP stale o
problema momentaneo di rete).

**Azione:** raggiungibile via HMP diretto. Chiedergli della pulizia.

## Stato finale

| Peer | Vecchio hmp.py | Pulito | Verificato |
|------|---------------|--------|-----------|
| peer70 (questo) | ? | Da fare | — |
| peer105 | ❌ Già fermo | ✅ Niente da fare | ✅ |
| peer106 | ❌ Già fermo | ✅ Pulito | ✅ |
| peer84 | ❌ Già fermo | ❓ Ha detto NO | Da approfondire |
| peer128 | ❌ Già fermo | ❓ Non contattato | ✅ HMP funziona |

## Lezioni apprese

1. **Il vecchio hmp.py standalone era già fermo ovunque** — nessun peer
   lo stava più eseguendo su :8643. I servizi systemd e cron job erano
   i soli residui superstiti.
2. **peer106 era l'unico con residui reali** — servizi systemd attivi
   (hmp-server, hmp-worker), file in /usr/local/bin/, watchdog cron job.
3. **peer105 è lento** — 40s per processare anche messaggi semplici.
   Sospetto: Fedora 30 (del 2019) su aarch64, modello grande?
4. **peer84 dice NO ma non si capisce perché** — il server non è in
   esecuzione, forse ha ancora file o processi dipendenti.
5. **peer128: broadcast fallisce, HMP diretto funziona** — il routing
   del broadcast (connessioni concorrenti?) ha problemi diversi dal
   singolo health check.
6. **Sempre verificare indipendentemente** — il resoconto del peer è
   auto-dichiarato, non sostituisce un health check reale.
