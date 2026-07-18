# HMP v0.1.3 — Producer-Consumer + Limite Lunghezza

## Novità

### 1. Producer-Consumer (fix stallo messaggi)
Prima: `POST /hmp/send` chiamava `handle_message()` inline, bloccando l'HTTP handler. Se l'agente era occupato, il messaggio restava in `working` per sempre.

Ora:
- **Producer** (HTTP): scrive in coda SQLite con `status=queued`, risponde subito 202
- **Consumer** (background loop): ogni 2 secondi prende il prossimo messaggio dalla coda e lo inoltra all'agente via `handle_message()`
- L'agente processa quando è scarico → `completed`
- Zero messaggi persi, zero stalli

### 2. Limite lunghezza messaggi (413 Payload Too Large)
I messaggi con `payload.text` più lungo di 2048 caratteri vengono rifiutati con **HTTP 413 Payload Too Large**.

Motivo: messaggi troppo lunghi saturano la sessione dell'agente, che smette di rispondere.

Configurabile via env `HMP_MAX_TEXT_LENGTH` (default: 2048).

### 3. Agent-card potenziato
`/hmp/agent-card` ora espone:
- `max_text_length`: limite in caratteri
- `version`: versione del plugin

## File modificati

- `adapter.py`: producer-consumer, 413 check, agent-card esteso
- `core.py`: metodi `queue()` e `dequeue()` per la coda SQLite
- `plugin.yaml`: version bump + env `HMP_MAX_TEXT_LENGTH`

## Versione

`0.1.3` (da `0.1.2`)

## Flusso distribuzione

1. peer70 implementa e testa ✅
2. Spiegare a UN peer via HMP (niente SSH)
3. Il peer fa: backup plugin → sostituisce i 3 file → restart gateway
4. Test bidirezionale
5. Se ok → peer successivo
