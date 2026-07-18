# Guardiano dell'Orchestratore — On-Demand Port Opening (Locale)

Pattern: l'orchestratore gestisce il proprio firewall (iptables) per aprire/chiudere una porta su richiesta, con auto-expiry e watchdog.

Questo è complementare al pattern "remoto" (guardiano su peer84). Qui il guardiano gira SULLO STESSO orchestratore.

## Quando Usarlo

- Hai un orchestratore 24/7 (RPi) e vuoi esporre SSH (o altro servizio) via port forwarding dal router
- La porta deve stare CHIUSA per default e aprirsi solo su richiesta (sicurezza)
- Non vuoi SSH sulla macchina target per gestirlo (paradosso bootstrap)
- Hai un cron watchdog che pulisce automaticamente dopo scadenza

## Architettura

```
Router (port forwarding WAN → LAN)
         │
         ▼  (forwarda porta esterna → peer70:2222)
┌─────────────────────┐
│  peer70 orchestrator │
│  ─────────────────── │
│  SSH su :22 (LAN)   │
│  SSH su :2222 (WAN) │  ← iptables blocca/aperta su richiesta
│  iptables: DROP     │
│    default          │
│                     │
│  guardiano-peer70   │
│  ├─ open (20 min)   │
│  ├─ close           │
│  ├─ keepalive       │
│  └─ watchdog (cron) │
└─────────────────────┘

Trigger:
  Utente → "apriti sedano" → peer70 esegue guardiano-peer70.sh open
  Utente → "Sisisi"        → peer70 esegue guardiano-peer70.sh keepalive
  (20 min)                  → watchdog auto-chiude
```

## Setup

### 1. SSH su doppia porta

Aggiungi un drop-in config in `/etc/ssh/sshd_config.d/`:

```bash
# /etc/ssh/sshd_config.d/port-forward.conf
Port 22
Port 2222
```

**ATTENZIONE:** Se metti SOLO `Port 2222`, SSH smette di ascoltare sulla 22. Devi listare esplicitamente TUTTE le porte che vuoi, inclusa la 22. OpenSSH non aggiunge, sostituisce quando c'è almeno una direttiva `Port`.

Verifica:
```bash
ss -tlnp | grep -E ':(22|2222) '
# Desiderato: 0.0.0.0:22 e 0.0.0.0:2222 su LISTEN
```

### 2. Script guardiano

Crea `~/.hermes/scripts/guardiano-peer70.sh` con queste funzioni:

| Funzione | Cosa fa |
|----------|---------|
| `open_port()` | Aggiunge `iptables -A INPUT -p tcp --dport 2222 -j ACCEPT`, salva state JSON con expiry |
| `close_port()` | Rimuove la regola iptables, cancella state e keepalive |
| `show_status()` | Legge state JSON, mostra tempo rimanente |
| `keepalive()` | Resetta il timer (riscrive state con +20 min) |
| `watchdog()` | Controllo automatico: se scaduto chiude, se keepalive presente resetta |
| `_bootstrap_iptables()` | Imposta baseline: DROP default, ALLOW established/loopback/LAN/ICMP |

**State format** (`/tmp/guardiano-peer70-state.json`):
```json
{
  "port": 2222,
  "opened_at": 1740000000,
  "expires_at": 1740001200,
  "duration": 1200
}
```

**Iptables baseline:**
```bash
# Policy di default
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP

# Sempre permessi
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -s 192.168.178.0/24 -j ACCEPT   # LAN
sudo iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT
```

**Idempotenza:** `_ipt_port_open()` e `_ipt_port_close()` controllano prima con `iptables -C` se la regola esiste già, per evitare duplicati o errori.

### 3. Cron watchdog

```python
cronjob(
    action="create",
    name="guardiano watchdog",
    schedule="every 1m",
    script="guardiano-peer70.sh watchdog",  # watchdog subcommand
    deliver="local",  # silenzioso
)
```

Il watchdog ogni minuto:
- Se il port è scaduto → chiude iptables + pulisce state
- Se c'è flag keepalive → resetta timer + rimuove flag
- Se mancano ≤2 min → logga avviso (visibile nei cron output)
- Se non c'è apertura attiva ma regola iptables ancora presente → la rimuove (cleanup)

### 4. Frase di attivazione

Il comando "apriti sedano" fa scattare `guardiano-peer70.sh open`. Non serve routing Telegram — l'agente sull'orchestratore esegue direttamente lo script locale.

## Pitfalls

- **`Port 2222` da sola sovrascrive la 22** — OpenSSD considera tutte le direttive `Port` come lista esaustiva. Includi sempre `Port 22` accanto alla nuova porta.
- **iptables non persistente** — le regole non sopravvivono a reboot. Aggiungere `iptables-persistent` o un systemd oneshot per il bootstrap, oppure riesegui `bootstrap` dopo ogni riavvio.
- **Timeout risposta API peer lento** — peer lenti (N56VV) richiedono `--max-time 90`. Per operazioni locali (guardiano sull'orchestratore), risposta istantanea.
- **Default policy ACCEPT** — su molti OS Linux (Raspberry Pi OS Desktop incluso) la policy INPUT di default è ACCEPT. Il bootstrap è obbligatorio per la sicurezza. Senza, la porta 2222 è già aperta e lo script non serve a nulla.
- **Keepalive window** — il keepalive resetta SOLO il timer, non cambia la durata. Ogni keepalive dà altri 20 min. Se servono sessioni lunghe, il client deve mandare keepalive periodici.
- **State file in /tmp** — /tmp è in memoria (tmpfs). Le aperture non sopravvivono a reboot. Dopo reboot, non ci sono state residue, ma la baseline iptables va reimpostata.

## Variazioni

- **Multi-porta:** estendi l'array delle porte per aprire più servizi (es. 2222 per SSH, 8642 per API Hermes)
- **Notifica Telegram:** il watchdog può mandare un messaggio quando la porta sta per scadere (invece di loggare solo)
- **Remote trigger:** se il guardiano è su un altro peer, usa il pattern "Cross-Peer API Actions" nella SKILL.md principale per triggerarlo via API Hermes
