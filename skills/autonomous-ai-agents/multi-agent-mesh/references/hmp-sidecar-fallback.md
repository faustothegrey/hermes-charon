# Sidecar Fallback Pattern

Pattern per configurare un peer Hermes come **hot standby** (Sidecar/muletto) del coordinatore primario. Quando il primario va giù, il Sidecar prende automaticamente le funzioni critiche.

## Architettura

```
Normale:                     Failover:
┌─────────┐    heartbeat     ┌─────────┐
│ Charon  │◄─── ogni 3m ────│ Sidecar │
│ (PRIMARIO)│    registry      │ (STANDBY)│
└─────────┘    sync ogni 30m  └─────────┘
     ▲                            ▲
     │ HMP                        │ HMP
     ▼                            ▼
  peer84,105,106,128         peer84,105,106,128
```

## Componenti

### 1. Heartbeat Watchdog
Cron job sul Sidecar che pinga il primario ogni 3 min:
- `curl -sf http://<primario>:18643/hmp/health` → timeout 5s
- 3 fallimenti consecutivi → attiva failover
- Quando il primario torna raggiungibile → auto-demozione

### 2. Registry Mirror
Cron job sul Sidecar ogni 30 min:
- Invia richiesta HMP al primario: "registry sync?"
- Salva risposta in `~/.hermes/registry/mirror.json`
- 3 fallimenti consecutivi → può attivare failover

### 3. Notifica Quotidiana Failover
Cron job giornaliero (es. 9:00) sul Sidecar:
- Se in failover → invia messaggio all'utente
- Se primario OK → silenzioso

### 4. FRITZ!Box TR-064
Il Sidecar deve poter gestire il router:
- `pip3 install fritzconnection` in venv dedicata
- Script `~/.hermes/scripts/fritzbox-portmgr.py` con list/add/del
- Router FRITZ!Box a 192.168.178.1, TR-064/UPnP accessibile senza password su LAN

### 5. Failover Logic
Se 3 fallimenti heartbeat consecutivi:
1. Promuovi Sidecar a registry temporaneo
2. Broadcast HMP ai peer: "registry ora su Sidecar 192.168.178.X"
3. Avvia monitoraggio peer
4. Ogni X min, riprova a contattare il primario
5. Se primario torna → demuovi, torna standby

## Quando NON usare
- Sidecar con <512MB RAM
- Rete singola non critica
- Sidecar senza HMP gateway

## Peer reali
| Peer | Ruolo | IP | HW |
|------|-------|-----|-----|
| Charon (peer70) | Primario | 192.168.178.70 | RPi4, 4GB |
| Sidecar (peer58) | Standby | 192.168.178.58 | RPi3B+, 1GB |

## Cron jobs Sidecar
| Nome | Schedule | Funzione |
|------|----------|----------|
| Heartbeat watchdog | ogni 3 min | Ping + failover |
| Registry mirror sync | ogni 30 min | Sincronizza registry |
| Daily failover notice | 0 9 * * * | Notifica utente |
