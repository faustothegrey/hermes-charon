# Pattern: Watchdog Messaggi Bloccati (Monitoraggio + Alert)

⚠️ **AGGIORNAMENTO 2026-07-17:** Lo script `hmp-watchdog.sh` su peer70 **non fa più auto-fail**.
La versione attuale **logga + invia alert HMP** a peer70. L'auto-fail è stato rimosso
perché in v0.1.3 il producer-consumer gestisce i messaggi in coda — i messaggi che
restano bloccati in "working" sono tipicamente di peer lightweight (Pi Agent/trixie_test)
che non completano la transizione di stato. L'alert serve per monitoraggio, non per
correzione automatica. Il reset manuale è sempre possibile via SQLite (vedi sotto).

## Problema originale

Quando l'agente Hermes su peer70 era impegnato in una catena di tool calls
(terminal, execute_code, SSH), un messaggio HMP in arrivo veniva inoltrato
dal plugin gateway alla chat dell'agente. L'agente lo vedeva, rispondeva
"I'll respond shortly", ma **non tornava mai a completarlo** perché il flusso
delle tool call proseguiva. Il messaggio restava in stato `working` per sempre
nel DB del gateway.

**RISOLTO in v0.1.3** con producer-consumer: l'HTTP handler scrive in coda
(`queued`) e torna subito; un consumer loop in background inoltra all'agente
quando è libero.

## Comportamento attuale del watchdog

Script `~/.hermes/scripts/hmp-watchdog.sh` (cron ogni 3 min, no_agent):

- Controlla il DB `/home/fausto/.hermes/data/hmp_gateway_plugin/messages.db`
- Cerca messaggi con `status='working'` più vecchi di 3 minuti
- **Logga** su `~/.hermes/logs/hmp-watchdog.log` con timestamp e dettagli
- **Alerta** via HMP a peer70 con JSON in `~/.hermes/logs/hmp-watchdog-alert.json`
- **NON modifica** lo stato dei messaggi (nessun auto-fail)
- Nessun output se non ci sono messaggi bloccati (cron silent)

## Reset manuale (quando serve)

Se un messaggio è visibilmente un test o un falso positivo e si vuole
sbloccarlo subito senza attendere il prossimo ciclo watchdog:

```sql
-- Via SQLite diretto
sqlite3 /home/fausto/.hermes/data/hmp_gateway_plugin/messages.db \
  "UPDATE hmp_gateway_messages SET status='failed', error='manually_failed_by_watchdog' \
   WHERE message_id='test_watchdog_1784285040' AND status='working'"
```

Verificare con:
```sql
SELECT message_id, from_peer, status, error FROM hmp_gateway_messages
WHERE message_id LIKE 'test_%' AND status='working';
```

## Perché i messaggi di test restano bloccati

I messaggi da peer lightweight (trixie_test, Pi Agent) possono rimanere
in `working` perché:

1. Il peer mittente invia e non polla mai per la risposta
2. Il peer mittente è un nodo di test che non implementa la macchina a stati completa
3. Il plugin HMP accetta il messaggio (→ `working`) ma nessun consumer lo completa
   perché il messaggio non è destinato a un agente che sa rispondere

In v0.1.2 questi messaggi sarebbero stati auto-failati dopo 3 minuti.
Con v0.1.3 + producer-consumer non bloccano più il gateway, quindi
l'auto-fail non serve — i messaggi orfani si accumulano ma non bloccano nulla.
Il watchdog li segnala per trasparenza.

## Retry lato client (peer mittente)

Il peer mittente può implementare `hmp_send_with_retry()` per gestire
timeout e fallimenti:

```
attempt 1: send + poll per 30s
  -> se completed: ok
  -> se failed/timeout: backoff 10s
attempt 2: send + poll per 30s
  -> se failed/timeout: backoff 20s
attempt 3: send + poll per 30s
  -> se fallito: log "tutti i tentativi falliti"
```

Parametri: `max_attempts=3`, `poll_interval=3s`, `base_timeout=30s`, `backoff_base=10s`.
2. Esegui `bash ~/.hermes/scripts/hmp-watchdog.sh`
3. Verifica che status sia `failed` con error `timeout_240s`
