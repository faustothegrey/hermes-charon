# 413 Payload Too Large — HMP v0.1.3

## Razionale

I messaggi HMP con `payload.text` più lungo di ~2KB saturano la sessione
dell'agente ricevente. L'agente non risponde più — il messaggio resta in
`working` per sempre.

**Causa:** l'agente Hermes ha un limite di contesto. Un messaggio troppo
lungo consuma una fetta enorme del token budget, l'agente non riesce a
processarlo, e la sessione si blocca.

## Soluzione: 413 Payload Too Large

Dal plugin v0.1.3, `_accept_hmp_message()` controlla `len(text)` prima di
accodare. Se supera `MAX_TEXT_LENGTH` (default 2048), risponde con HTTP 413.

## Configurazione

```bash
# Via env var (permanente in plugin.yaml o ambiente)
export HMP_MAX_TEXT_LENGTH=4096  # default: 2048
```

## Comportamento

### Richiesta troppo lunga
```json
POST /hmp/send
→ 413 Payload Too Large
→ {"accepted": false, "error": "text_too_long", "detail": "max 2048 chars, got 3000"}
```

### Richiesta normale
```json
POST /hmp/send
→ 202 Accepted
→ {"accepted": true, "status": "queued", "message_id": "msg_..."}
```

## Agent-card

L'endpoint `/hmp/agent-card` espone il limite per trasparenza:

```json
{
  "agent": "peer70",
  "max_text_length": 2048,
  "version": "0.1.3"
}
```

## Cosa NON va in HMP (usa altri canali)

| Contenuto | Canale alternativo |
|-----------|-------------------|
| File di codice lunghi (>2KB) | Base64 in messaggi multipli, o scp (solo emergenza) |
| Log estesi | Riferimento a path locale |
| Documentazione lunga | Link a vault o skill |
| Script interi | Inviare in blocchi o via scp |
