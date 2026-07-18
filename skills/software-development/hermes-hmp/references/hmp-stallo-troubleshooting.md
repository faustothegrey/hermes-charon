# Stallo messaggi HMP — troubleshooting completo

## Storia del bug (2026-07-17)

Trixie (nuovo nodo RPi3B+) invia un messaggio HMP a peer70. Peer70 è occupato
con tool calls. Il messaggio viene accettato (status=working) ma l'agente
scrive "I'll respond shortly" e non torna mai a completarlo. Il mittente
resta in attesa per sempre.

## Root cause

`_accept_hmp_message()` in `adapter.py` chiamava `await self.handle_message(event)`
**inline** nell'HTTP handler. Se l'agente era occupato, la await bloccava
l'handler e il messaggio restava in `working` senza mai passare a `completed`.

La risposta "I'll respond shortly" era un effetto collaterale: l'agente Hermes
vede un messaggio in arrivo mentre esegue tool, genera un'interruzione
automatica, ma non torna mai a elaborare la richiesta originale.

## Fix: producer-consumer (v0.1.3)

- HTTP handler (producer): scrive in coda SQLite con status `queued`, torna subito 202
- Consumer loop (background): ogni 2 secondi prende il prossimo messaggio dalla coda
  e lo inoltra all'agente via `handle_message()`
- Se l'agente è occupato, il consumer aspetta il ciclo successivo
- Un messaggio alla volta — mai più di uno in elaborazione parallela

File modificati in `~/.hermes/plugins/hmp/`:
- **core.py**: aggiunti metodi `queue()` e `dequeue()` per la coda SQLite
- **adapter.py**:
  - `_accept_hmp_message()` usa `store.queue()` invece di `accept()` + `handle_message()` diretto
  - Aggiunto `_consumer_loop()` — asyncio task che polla ogni 2s
  - Avviato in `connect()` con `asyncio.ensure_future()`
  - Fermato in `disconnect()` con `cancel()`
- **plugin.yaml**: version bump 0.1.2 → 0.1.3

## 413 Payload Too Large

Contemporaneamente: messaggi HMP con `payload.text` > 2048 caratteri saturano
l'agente e causano stallo. Aggiunto controllo in `_accept_hmp_message()`:
se `len(text) > MAX_TEXT_LENGTH`, risponde con HTTP 413 senza accodare.

Configurabile via env `HMP_MAX_TEXT_LENGTH`. Esposto in `/hmp/agent-card`.

## La lezione

**La toppa va sul peer che si è rotto, non su quello che ha chiamato.**
Tentativo iniziale: aggiungere retry con backoff su Trixie (mittente).
Corretto dal user: il problema era su peer70 (ricevente), quindi la soluzione
va su peer70.

## Distribuzione plugin — flusso corretto

1. Implementa/modifica su peer70 (source of truth)
2. Testa localmente: health, agent-card, send+poll, 413
3. Bump versione in plugin.yaml
4. Spiega a UN peer via HMP (messaggio breve! <500 char)
5. Il peer fa: backup → sostituisce file → touch *.py → restart gateway
6. Test bidirezionale
7. Se ok → peer successivo

**Niente SSH.** I peer sono agenti autonomi. SSH solo in emergenza.

## Pitfall: .pyc cache

Su peer106, dopo aver copiato i nuovi file .py, il gateway continuava a
caricare il codice vecchio. Causa: Python 3.11 usava il .pyc in `__pycache__/`
che aveva un timestamp uguale al .py. Non ricompilava.

Soluzione: cancellare __pycache__ e fare `touch *.py` prima del restart.
Includere `touch` nelle istruzioni di upgrade.

## Pitfall: restart su peer106 (Fedora)

`systemctl --user restart` a volte lascia il processo in `deactivating`
per minuti. Usare invece:

```bash
kill -9 <PID>
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway
```
