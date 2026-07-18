# Pattern: Investigazione Alert Watchdog HMP

Quando ricevi un alert dal watchdog di peer70 ("⚠️ Watchdog: N messaggio/i HMP
bloccato/i in 'working' da >3 min"), segui questa procedura sistematica per
determinare se è un problema reale o un falso positivo transiente.

## 1. Leggi il file alert JSON

```bash
cat /home/fausto/.hermes/logs/hmp-watchdog-alert.json
```

Contiene: timestamp, conteggio, array di messaggi con `message_id`, `from`,
`stuck_seconds`.

## 2. Leggi il log storico del watchdog

```bash
cat /home/fausto/.hermes/logs/hmp-watchdog.log
```

Mostra la cronologia completa: messaggi già auto-failati in passato (`AUTOFAIL`),
alert attuali, e pattern di ricorrenza. Utile per capire se è un problema
persistente o nuovo.

## 3. Verifica la cronologia recente del cron job

```bash
# Lista tutti i run del watchdog
ls -lt ~/.hermes/cron/output/<job_id>/
```

Ogni file .md contiene l'output del watchdog a quell'orario. Controlla:
- **"silent (empty output)"** → nessun blocco a quell'ora
- **messaggio con ⚠️** → blocco rilevato a quell'ora

Costruisci la timeline:

| Ora | Output | Interpretazione |
|-----|--------|-----------------|
| 12:44 | ⚠️ bloccato | Problema rilevato |
| 12:48 | silent | Risolto |
| 12:51 | silent | Conferma |

## 4. Leggi lo script watchdog per il meccanismo

```bash
cat ~/.hermes/scripts/hmp-watchdog.sh
```

Punti chiave da estrarre:
- **DB path**: dove il watchdog cerca i messaggi bloccati
- **Soglia**: minuti prima che un messaggio sia considerato bloccato
- **Azione**: auto-fail o solo log+alert (attuale: solo log+alert)
- **Esclusioni**: messaggi da `watchdog` stesso sono esclusi dalla ricerca

## 5. Cross-referenzia con la situazione attuale

Se l'ultimo run del watchdog è silenzioso → il problema si è autorisolto.

**Pattern comune:** messaggi di TEST da peer lightweight (trixie_test, Pi Agent)
che non completano la transizione di stato → il watchdog li segnala, ma dopo
qualche minuto scompaiono da soli (o perché il peer li completa, o perché
il consumer cycle li processa).

## 6. Quando intervenire

| Scenario | Azione |
|----------|--------|
| Messaggio di test (`test_*`), transiente | Nessuna — si autorisolve |
| Messaggio di test persistente (>4 cicli watchdog) | Reset manuale via SQLite (vedi `hmp-watchdog-retry.md`) |
| Messaggio reale (non test) bloccato | Investigare il peer mittente: è online? Ha il plugin funzionante? |
| Più messaggi reali bloccati | Possibile problema sul consumer loop HMP — verificare gateway status |

## 7. Reset manuale (quando necessario)

```sql
sqlite3 /home/fausto/.hermes/data/hmp_gateway_plugin/messages.db \
  "UPDATE hmp_gateway_messages SET status='failed', error='manually_failed' \
   WHERE message_id='<id>' AND status='working'"
```

## Riferimenti

- `hmp-watchdog.sh` — script watchdog attivo su peer70
- `hmp-watchdog-retry.md` — pattern storico con dettagli reset manuale
- `hmp-diagnostics.md` — diagnostica peer per messaggi realmente bloccati
