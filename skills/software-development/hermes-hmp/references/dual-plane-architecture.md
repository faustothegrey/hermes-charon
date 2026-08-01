# Dual-Plane Architecture (v2.0.0-alpha)

Protocollo HMP dual-plane: API sessions (`:8642`) come data plane,
HMP (`:18643`) come control plane. Sessioni trasparenti, harness
astratto per l'agente.

## Principio Fondamentale

L'agente fa **UNA** sola chiamata HTTP (HMP `:18643`).
L'harness gestisce internamente tutto il resto.

```
AGENTE:       1 chiamata HMP :18643    ← "come Telegram client"
                     │
HARNESS:             │
  ├─ Cerca/crea sessione API (:8642)   ← invisibile
  ├─ Invia contenuto nella sessione    ← invisibile
  ├─ Invia notifica HMP leggera        ← invisibile
  └─ Retry 3x + alert se fallisce     ← invisibile
```

## Perché il dual-plane?

HMP da solo NON può creare sessioni agente. Ogni messaggio HMP
finisce in una sessione agente casuale — nessun contesto preservato.

API `:8642 /api/sessions` è l'unico modo per creare una sessione
Hermes reale con contesto e cronologia (come una chat Telegram).

## Sessioni Trasparenti

Ogni coppia di peer → una sessione API dedicata. Identificata da
`peer_pair_id` (ordinato lessicograficamente: `peer70_peer105`).

Il `peer_pair_id` è l'equivalente del `chat_id` di Telegram:
- Viene creato al primo messaggio tra due peer
- Riusato automaticamente per tutti i messaggi successivi
- Preserva contesto e cronologia
- **Invisibile** a chi invia e riceve — gestito dall'harness

## Flusso: peer70 → peer105

```
1. peer70 chiama HMP :18643 /hmp/send
   → harness intercetta la richiesta

2. Harness cerca/crea sessione API su peer105:
   GET  /api/sessions?peer_pair_id=peer70_peer105
   POST /api/sessions (se nuova)

3. Harness invia messaggio nella sessione:
   POST /v1/chat/completions { "session_id": "...", "messages": [...] }

4. Harness invia notifica HMP leggera:
   POST :18643 /hmp/send → "NEW_API_SESSION_MESSAGE ..."

5. peer105 riceve notifica HMP, recupera il messaggio
   dalla propria sessione API locale, lo processa.

6. peer105 risponde (stesso flusso inverso).
```

## Notifica con Retry

```python
tentativo 1 → timeout/errore → attesa 2s
tentativo 2 → timeout/errore → attesa 5s
tentativo 3 → timeout/errore → attesa 10s
se tutti falliti → HMP alert al peer destinatario
```

## Fallback

Se `:8642` non risponde su peer105, l'harness manda il testo
completo via HMP classico (`:18643 /hmp/send` con `payload.text`).

## Implementazione

- `~/.hermes/scripts/hmp-dual-plane.py` — coordiantor-side (peer70)
- `~/.hermes/scripts/hmp_dual_plane.py` — alias underscore per import Python
- Session store: SQLite WAL in `~/.hermes/data/hmp/dual-plane.db`
- API keys: `~/.hermes/peer-network/peer-api-keys.json` (chmod 600)

## Stato

v2.0.0-alpha — testata su peer70 ↔ peer106. Non in produzione.
