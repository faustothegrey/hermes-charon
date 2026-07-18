---
name: hmp-anti-stallo
description: Producer-consumer pattern per evitare messaggi HMP bloccati. L'HTTP handler scrive in coda SQLite, un consumer loop inoltra all'agente quando è scarico.
type: custom
version: 1.2.0
---

# HMP Anti-Stallo — Producer-Consumer

## Principio fondamentale

**La toppa va sul peer che si è rotto, non su quello che ha chiamato.**

Se peer70 lascia messaggi bloccati `working`, la soluzione va su peer70 — non si aggiunge retry ai mittenti.

## Il problema (old way)

Prima di v0.1.3, `_accept_hmp_message()` chiamava `await self.handle_message(event)` **inline** nell'HTTP handler. L'handler restava bloccato finché l'agente non rispondeva. Se l'agente era occupato, il messaggio restava `working` per sempre.

## La soluzione: Producer-Consumer (v0.1.3+)

### Producer (HTTP handler) — `_accept_hmp_message()`
- Scrive il messaggio nel DB con status `queued`
- Torna subito 202
- Zero attesa, zero blocchi

### Consumer (background asyncio task) — `_consumer_loop()`
- Ogni 2 secondi chiama `store.dequeue()`
- Prende il prossimo messaggio `queued`, lo marca `delivering`
- Crea il `MessageEvent` e chiama `handle_message()` (l'agente lo vede in chat)
- Marca `working`
- Un messaggio alla volta — se l'agente è occupato, il consumer aspetta che `handle_message()` torni

### Flusso stati

```
queued → delivering → gateway_accepted → working → completed / failed
```

- **queued**: in coda, non ancora preso in carico
- **delivering**: preso dal consumer, sta per essere inoltrato
- **gateway_accepted, working**: gestito dall'agente
- **completed / failed**: risposta data o errore

### Codice

**`core.py`** — `HMPStatusStore`:
```python
def queue(self, message_id, body, from_peer, to_peer, text):
    # INSERT con status='queued'

def dequeue(self):
    # SELECT * WHERE status='queued' ORDER BY accepted_at LIMIT 1
    # UPDATE status='delivering' WHERE message_id=?
    # return item
```

**`adapter.py`** — `HMPAdapter`:
```python
async def _accept_hmp_message(self, request, body):
    # ... validazione ...
    self.store.queue(message_id, body, from_peer, to_peer, text)
    return {"accepted": True, "message_id": message_id, "status": "queued"}, 202

async def _consumer_loop(self):
    while True:
        await asyncio.sleep(2)
        item = self.store.dequeue()
        if not item:
            continue
        # ... build MessageEvent ...
        await self.handle_message(event)
        self.store.mark_status(message_id, "working")
```

### Upgrade da v0.1.2 a v0.1.3

Spiegare al peer cosa fare (niente SSH):

1. Backup: `cp -r ~/.hermes/plugins/hmp ~/.hermes/plugins/hmp.bak`
2. Aggiungere `queue()` e `dequeue()` a `core.py`
3. Aggiungere `_consumer_loop()` e modificare `_accept_hmp_message()` in `adapter.py`
4. Bump `plugin.yaml` a `version: 0.1.3`
5. Aggiungere `connect/disconnect` handler per consumer task
6. Riavviare il gateway: `systemctl --user restart hermes-gateway`
7. Verificare: `curl http://localhost:18643/health`
8. Test: POST /hmp/send → deve rispondere `"status": "queued"`

## Regola d'oro: niente SSH

**NON usare SSH per interventi su peer remoti.** Spiegare al peer cosa deve fare e lasciare che lo implementi da solo. SSH solo in casi critici (server down, recovery, emergenza).

I peer sono agenti autonomi, non terminali remoti.

## Watchdog (deprecato)

Il watchdog `hmp-watchdog.sh` era una soluzione tampone per auto-fallire messaggi bloccati. Con v0.1.3 non serve più — la coda producer-consumer risolve il problema alla radice. Tenuto per compatibilità, ma il cron può essere rimosso.

## Flusso distribuzione plugin

Vedi `references/distribuzione-plugin.md` per il workflow completo di distribuzione di una nuova versione del plugin HMP ai peer della rete.
