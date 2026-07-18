# Flusso Distribuzione Plugin HMP

## Regola d'Oro
**Niente SSH per interventi sui peer remoti.** Solo spiegare via HMP e lasciare che il peer esegua da solo. SSH **solo** in casi critici (server down, recovery, emergenza). I peer sono agenti autonomi, non terminali remoti.

## Il Flusso (da ricordare sempre)

```
1. Implementa/modifica su peer70   ← sorgente
2. Testa localmente su peer70
3. Bump versione in plugin.yaml
4. Spiega a UN peer via HMP cosa fare
5. Il peer si aggiorna da solo (sostituisce file, riavvia gateway)
6. Test bidirezionale con quel peer
7. Se OK → passa al peer successivo
8. Se KO → fix su peer70, ripeti dal punto 1
```

## Perché

- peer70 è la **source of truth** del plugin HMP
- Ogni peer è indipendente e sa auto-aggiornarsi
- L'errore va fixato **dalla parte che si è rotta**, non spostato sugli altri
- Il deployment graduale (1 peer alla volta) permette di rilevare problemi prima di espandere

## Versione Corrente

HMP plugin v0.1.3 — producer-consumer:
- **Producer** (HTTP handler): scrive in coda `status=queued`, risponde subito 202
- **Consumer** (background loop): ogni 2s prende dalla coda e inoltra all'agente
- Messaggi mai persi, mai bloccati in `working` per sempre
