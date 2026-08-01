# NetBoard Priority Message Queue

Sistema di coda messaggi prioritaria per display framebuffer su /dev/fb0.
Integrato in netboard.py tramite lock file JSON.

## Architettura

```
netboard-msg "testo" --priority N --duration D --sub "sottotitolo"
       │
       ▼
~/.hermes/netboard_queue.json  ← coda persistente (JSON con lock)
       │
       ▼
netboard.py  ← ogni ciclo (~1s) chiama netboard_queue.cmd_active()
       │
       ▼
Se active_msg → netboard_overlay.draw_overlay() → fb_write_rgb565()
Se None      → dashboard normale / screensaver
```

## Regole

- **Priorità 1-100**: più alto = più importante
- **Preempt**: se arriva un msg con priorità maggiore di quello attivo, lo sostituisce SUBITO
- **Scadenza**: ogni messaggio ha una durata in secondi. Quando scade, sparisce
- **Fallthrough**: quando il messaggio attivo scade, torna alla dashboard normale
- **Lock**: accesso con file lock (~/.hermes/netboard_queue.json.lock) per evitare race condition

## CLI

```bash
netboard-msg "Ciao mondo!"                          # priorità 5, 30s
netboard-msg "Allarme!" --priority 100 --duration 60 # urgente, 1 minuto
netboard-msg "Info" --priority 3 --sub "sottotitolo" # bassa priorità
netboard-msg list    # vedi coda
netboard-msg clean   # rimuovi scaduti
netboard-msg active  # mostra messaggio attivo (JSON)
```

## File del sistema

| File | Path | Ruolo |
|------|------|-------|
| `netboard_queue.py` | `~/.hermes/scripts/` | Gestione coda + CLI |
| `netboard_overlay.py` | `~/.hermes/scripts/` | Disegna messaggio su immagine |
| `netboard-msg.sh` | `~/.hermes/scripts/` | Wrapper CLI → symlink in /usr/local/bin/ |
| `netboard_queue.json` | `~/.hermes/` | Coda persistente |
| `netboard.py` | `~/.hermes/scripts/` | Integrazione (check coda a ogni ciclo) |
