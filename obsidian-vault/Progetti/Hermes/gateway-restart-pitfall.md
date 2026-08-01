# Gateway Restart: Non Fare `systemctl restart` da Dentro il Gateway

**Data:** 2026-07-30
**Scoperto su:** peer84 (N56VV, Ubuntu)

## Il Problema

Quando l'agente Hermes è in esecuzione (CLI o gateway), eseguire `systemctl --user restart hermes-gateway` da un `terminal()` o `delegate_task()` all'interno della sessione del gateway **causa SIGKILL a tutto il processo**.

Il gateway riceve SIGTERM, poi systemd manda SIGKILL all'intero albero dei processi (incluso lo script bash che esegue `systemctl`). Il gateway muore senza completare il restart.

## Sintomi

- `systemctl --user status hermes-gateway` mostra: `active: failed (Result: signal)`
- Log: `Sent signal SIGKILL to main process ... on client request`
- L'upgrade o altra operazione rimane incompleta

## Causa

Il gateway Hermes è un processo systemd `--user`. Quando l'agente (che gira dentro il gateway) esegue `systemctl restart hermes-gateway`, chiede a systemd di killare il suo stesso albero processi. systemd lo fa senza pietà.

## Soluzione

Sempre usare una shell **esterna** al gateway per riavviarlo:

```bash
# Da SSH sul peer
sshpass -p '<password>' ssh fausto@<peer-ip> "systemctl --user restart hermes-gateway"

# O da un cron system (crontab -e), non hermes cron
# O da un terminale separato sul peer (non terminal() dell'agente)
```

Non funzionano:
- `terminal("systemctl --user restart hermes-gateway")` ❌
- `delegate_task(goal="restart gateway")` ❌
- `background=true` con `systemctl restart` ❌

Funziona:
- SSH da un altro peer ✅
- Shell fisica sul peer ✅
- Crontab system (crontab -e) ✅

## Riferimenti

- Documentato in `multi-agent-mesh` skill → "Pitfalls" → "Gateway restart bloccato"
- Il plugin gateway HMP (`~/.hermes/plugins/hmp/`) non ha hook per graceful restart
