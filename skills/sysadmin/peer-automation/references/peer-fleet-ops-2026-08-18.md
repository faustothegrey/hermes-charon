# Peer fleet ops — 2026-08-18

Matrice operativa del mesh Hermes di Fausto, verificata live il 17-18/08.

## Matrice SSH (da peer70/Charon)

| Peer | IP | User SSH | Hostname | OS | Stato |
|---|---|---|---|---|---|
| peer70 | 192.168.178.70 | (locale) | Charon | RPi4 Debian | 24/7, orchestratore |
| peer106 | 192.168.178.106 | **root** (fausto rifiutato) | Trixie | Fedora ARM | offline da 14/08, upgrade pendente |
| peer128 | 192.168.178.112 | fausto | MacPro | macOS (launchd, non systemd) | **fluttuante** (portatile) |
| peer136 | 192.168.178.136 | fausto | **Davon** | Debian 13 trixie aarch64 | online, nuovo nel registry (17/08) |
| peer138 | 192.168.178.138 | root | DietPi | DietPi | online |
| peer141 | 192.168.178.141 | fausto | Stella | — | online, Hermes 0.20.1 |
| peer58 | 192.168.178.58 | fausto | Sidecar | — | online |
| peer84 | 192.168.178.84 | (verificare) | N56VV | Ubuntu | offline per finestre cooling (11-17, 02-03) |
| peer105 | ~~192.168.178.105~~ | — | — | — | **RIMOSSO 17/08** — non usare |

Regole:
- Sempre `BatchMode=yes` (solo chiavi, niente password interattiva).
- peer106: `fausto` viene rifiutato (`Permission denied publickey`) — usare `root`.
- peer128: il comando `timeout` NON esiste su macOS/zsh — non usarlo negli SSH verso peer128.

## Mappa versioni Hermes (17/08)

| Peer | Hermes |
|---|---|
| peer70 | 0.17.0 |
| peer106 | 0.20.2 |
| peer136 (Davon) | 0.20.2 (venv; API :8642 non esposta) |
| peer138 | 0.19.0 |
| peer141 | 0.20.1 |
| peer58 | 0.19.0 |

Verifica: `curl :8642/health` → `version`; fallback SSH `hermes --version` o
`~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main --version`.

## Registrazione di un nuovo peer nel Local Skill registry

Procedura usata per peer136/Davon (17/08):
1. `registry.json` → chiave `peers["peer136"] = {"host": "192.168.178.136", "skills": [], "plugins": [], "skill_count": 0}` + `updated_at` UTC.
2. `peers/peer136.json` → manifest (host, hostname, os, user, plugins=["hmp"], updated_at).
3. Notificare la definizione ai peer attivi via HMP (REGISTRY NOTICE → memoria dei peer).
4. Aggiornare memoria locale con il nuovo peer.

## Caso Davon (peer136) — conflitto porta HMP

- Hostname macchina = "Diet", nome peer = **Davon**, servizio custom = **Trixie** (`trixie-hmp.service` +
  `trixie-watchdog.sh` cron ogni 5 min, `hmp-server.py` pi.dev-agent).
- Il servizio Trixie occupava :18643 → il gateway Hermes di Davon girava ma SENZA porta HMP (solo Telegram).
- 18/08 su richiesta Fausto: `systemctl stop+disable trixie-hmp.service` + riga watchdog rimossa dal crontab
  → porta libera. Plugin hmp NON installato su Davon (niente `~/.hermes/plugins/`) → resta nodo solo-Telegram
  finché non si copia il plugin (decisione Fausto: lascia così).
- Modello Davon cambiato in config: `deepseek/deepseek-v4-flash` / provider `nous` /
  `https://inference-api.nousresearch.com/v1` (era `gpt-5.6-luna` / `openai-codex`). Backup config creato.

## Lezione identità

`hostname` della macchina ≠ nome del peer ≠ nome di un servizio custom. Su Davon: hostname="Diet",
peer="Davon", servizio="Trixie". Sempre chiedere/verificare il nome vero del peer (Fausto corregge).
