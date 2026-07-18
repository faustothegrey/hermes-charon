# HMP Brainstorm — Gang Idea Machine

Script in `~/.hermes/scripts/hmp-brainstorm.py`.

## Uso da execute_code()

```python
exec(open('/home/fausto/.hermes/scripts/hmp-brainstorm.py').read())
result = brainstorm("Tema", "Domanda?", max_rounds=3)
```

## Flusso

1. Invia domanda a tutti i peer (84, 105, 106, 128)
2. Raccoglie risposte (max 3-4 frasi, ACTIONABLE)
3. Sintesi delle idee
4. Votazione GO/NO GO sulla sintesi
5. Se non c'è consenso → round successivo con obiezioni
6. Max 3 round
7. Votazione finale → report con consenso o no

## Peer speciali

- **peer128**: non raggiungibile da execute_code() (sandbox Python). Usare `curl` + poll manuale per peer128.
- **peer105**: lento (30-60s per rispondere). Impostare `max_polls=40, poll_interval=5`.
