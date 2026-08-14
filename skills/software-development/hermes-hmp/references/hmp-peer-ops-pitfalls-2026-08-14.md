# HMP Peer-Ops Pitfalls (2026-08-14)

Lezioni operative dalla sessione di allineamento rete (deploy hmp 0.1.4 su
peer138/141, verifica bidirezionale, sblocco sessione bloccata).

## 1. `send_and_wait` va in timeout su task lunghi — il messaggio arriva comunque

`/hmp/send_and_wait` con `timeout` oltre ~120-300s scade PRIMA che il peer
finisca (implementazione plugin + restart + smoke test = 300-400s reali).
Sintomo: curl `--max-time` scade, risposta persa — MA il messaggio è stato
consegnato e il peer lavora comunque.

**Pattern di recovery (3 round):**
1. Verifica via SSH lo stato reale del peer (file modificati, git diff, log gateway) — non fidarti del timeout
2. Se il peer ha completato (log `response ready` con chars alte), chiedi il **report compatto** con un nuovo `send_and_wait`: `"Rispondi COMPATTO max 600 caratteri: CAUSA: | FIX: | ESITO:"`
3. Se il peer è impegnato su altro (risponde con redirect), aspetta e riverifica via SSH

## 2. `plugins.enabled` come stringa JSON rompe la registrazione delle piattaforme

Sintomo: dopo un riavvio gateway, HMP giù e log con:
```
Skipping invalid routing entry 'agent:main:hmp:dm:peer70': 'hmp' is not a valid Platform
```

Causa: config scritto come stringa invece di lista YAML:
```yaml
# SBAGLIATO — il parser non la riconosce come lista di plugin
plugins:
  enabled: '["hmp", "harness-feedback"]'

# GIUSTO
plugins:
  enabled:
    - hmp
    - harness-feedback
```
Verifica rapida: `grep -A4 '^plugins:' ~/.hermes/config.yaml` e confronta col
formato di peer70. Fix: riscrivere come lista YAML + riavvio gateway.

## 3. Sessione HMP bloccata (turno appeso) — recovery

Sintomo: messaggio da peer in `delivering` per ore, nessuna `response ready`
nel log, sessione con `last_prompt_tokens` alto (200K+). Il turno è appeso su
una chiamata LLM dentro il processo gateway.

**Il riavvio del gateway risolve**: il turno appeso muore col processo, la
coda messaggi si svuota (verifica `agent_messages.db` status
`delivering/working/pending` = 0), e il peer può rilanciare il task.
La sessione NON va resettata: resta grande ma sotto soglia (compressione 50%,
watchdog 70%) e conserva il contesto.

## 4. Restart gateway su peer remoti — mappa per peer

| Peer | Tipo servizio | Processo (pgrep) | Comando restart |
|---|---|---|---|
| peer70/141 | systemd user | `hermes_cli.main gateway` | script kill + `systemctl --user start` |
| peer138 (DietPi) | systemd DI SISTEMA | `/usr/local/lib/hermes-agent/hermes gateway` | kill + `systemctl restart hermes-gateway` (no --user) |
| peer58 | systemd user | `hermes_cli.main gateway` | script standard |

Nota: `pgrep -f 'hermes_cli.main gateway'` NON trova il processo su peer138
(install pip con path diverso) — il kill non avviene, il gateway resta sul
codice vecchio. Health check su DietPi richiede ~30s di startup: il check
immediato dà DOWN, riverificare dopo 30s.
