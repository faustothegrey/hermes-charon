# Sidecar (peer58) — Fallback Pattern

Il pattern Sidecar definisce un **nodo di riserva** per Charon (peer70).
Sidecar (peer58) è un Hermes Agent su Raspberry Pi 3B+ (Debian 13) che
funge da hot standby per le operazioni critiche.

## Quando è stato stabilito

2026-07-18 — Charon ha contattato Sidecar via HMP per organizzare il
fallback. Sidecar ha implementato tutto in autonomia.

## Ruolo

| Funzione | Attiva su Charon | Su Sidecar (fallback) |
|----------|-----------------|----------------------|
| Orchestratore rete | ✅ Primario | ❌ Solo se Charon cade |
| Registry HMP | ✅ Primario | ✅ Mirror, promozione su failover |
| Heartbeat peer | ✅ Ping round ogni 10 min | ✅ Watchdog ogni 3 min |
| FRITZ!Box portmgr | ✅ Script | ✅ Script clonato |
| NetBoard display | ✅ (800x480 DSI) | ❌ Nessun display |
| Daily Exchange | ✅ Coordinatore | ✅ Solo digest (ruolo leggero) |

## Cosa ha implementato Sidecar autonomamente

1. **Heartbeat watchdog** (cron ogni 3 min, job `1507eec3d768`)
   - `curl http://192.168.178.70:18643/hmp/health`
   - 3 fallimenti consecutivi → attiva failover
   - Salta peer84 nelle finestre cooling (11-17, 02-03)

2. **Registry mirror** (cron ogni 30 min, job `fd2d98a92480`)
   - Chiede sync a Charon via HMP
   - Salva in `~/.hermes/registry/mirror.json`
   - 3 fallimenti consecutivi → promozione a registry primario

3. **Notifica failover** (cron 9:00, job `98ee747066fa`)
   - Silenziosa se Charon è online
   - Se in failover: "Charon ancora giù, Sidecar attivo"

4. **FRITZ!Box TR-064**
   - `pip install fritzconnection` in venv dedicata
   - Script `~/.hermes/scripts/fritzbox-portmgr.py`
   - Comandi: `list`, `add <port> <IP> [TCP/UDP] [name]`, `del <port> [TCP/UDP]`

## Meccanismo di failover

```
Charon cade (3 heartbeat falliti consecutivi)
  └── Sidecar:
      1. Si promuove a registry su 192.168.178.58:18643
      2. Broadcast HMP ai peer: "registry ora su Sidecar"
      3. Attiva notifica quotidiana all'utente
      
Charon torna online
  └── Sidecar:
      1. Rileva Charon raggiungibile via heartbeat
      2. Si demuove automaticamente
      3. Torna in modalità mirror/standby
```

## Script lato Sidecar

Sidecar ha creato autonomamente:
- `~/.hermes/scripts/hmp_sidecar.py` — watchdog principale
- `~/.hermes/scripts/hmp_sidecar_heartbeat.sh` — wrapper heartbeat
- `~/.hermes/scripts/hmp_sidecar_registry_sync.sh` — wrapper registry sync
- `~/.hermes/registry/sidecar_state.json` — stato locale

## Comunicazione con Sidecar

Standard HMP v0.1.3 su `192.168.178.58:18643`.

**Latenza**: ~162ms (RPi 3B+ via WiFi o Ethernet, più lento di Charon).
**Timeout consigliato**: 120-180s per messaggi che richiedono elaborazione.

## Limiti Sidecar (RPi 3B+)

- RAM: ~1GB — niente elaborazione pesante
- No display — niente NetBoard
- No Daily Exchange consolidator — solo invio digest
- CPU: ARM Cortex-A53 quad-core 1.2GHz
