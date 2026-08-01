# HMP Sidecar / Fallback Node

## Concetto

Un **Sidecar** (o fallback node) è un peer HMP secondario con Hermes Agent che monitora il primario e ne prende le funzioni critiche quando il primario non è raggiungibile. Pattern di **high availability** per la rete Hermes.

**Differenza dal lightweight peer**: un lightweight peer parla HMP ma non ha Hermes Agent. Un Sidecar ha Hermes Agent completo ed è pronto a sostituire il primario in operazioni critiche (registry, monitoring, FRITZ!Box).

## Architettura

```
CHARON (primario, RPi4)  ◄──heartbeat 3min──►  SIDECAR (fallback, RPi3+)
                              registry sync 30m
```

## Componenti

### 1. Heartbeat watchdog
Cron ogni 3 min sul Sidecar: `curl http://<primario>:18643/hmp/health`
Dopo 3 fallimenti consecutivi → attiva failover.

### 2. Registry mirror sync
Cron ogni 30 min. Sidecar invia "registry sync?" via HMP, salva JSON in `~/.hermes/registry/mirror.json`.
3 fallimenti consecutivi → attiva failover.

### 3. Failover promotion
- Sidecar si promuove a registry temporaneo
- Broadcast HMP: "registry ora su Sidecar IP"
- Attiva monitoring peer
- Notifica quotidiana (cron 9:00): "Charon ancora giù, Sidecar attivo"

### 4. Demotion
Quando il primario torna raggiungibile, Sidecar si demuove automaticamente e torna mirror.

## Cosa può fare un Sidecar (RPi3+)

| Funzione | OK? | Note |
|----------|-----|------|
| Heartbeat | ✅ | Curl ogni 3 min, leggerissimo |
| Registry mirror | ✅ | JSON via HMP, pochi KB |
| FRITZ!Box TR-064 | ✅ | `pip install fritzconnection`, script `fritzbox-portmgr.py` |
| Peer monitoring | ✅ | Ping round leggero |
| Notifiche utente | ✅ | Cron quotidiano |
| NetBoard | ❌ | Nessun display |
| Exchange consolidator | ❌ | Troppo pesante per RPi3+ |

## Peer conosciuti

| ID | IP | Ruolo | OS |
|----|-----|-------|-----|
| peer70/Charon | 192.168.178.70 | Primario | RPi4 Debian 11 |
| peer58/Sidecar | 192.168.178.58 | Fallback | RPi3+ Debian 13 |
