# Peer-mesh send pattern (2026-08-15)

Come inviare un MESSAGGIO reale a un peer della mesh HMP (usato per gli e2e
mesh: requester → executor) e come NON farlo.

## `/hmp/send` sul PROPRIO gateway = INIEZIONE LOCALE (non invio)

`POST http://<self>:18643/hmp/send` chiama `BasePlatformAdapter.handle_message()`
(adapter.py): il messaggio viene **eseguito dal proprio agente** e compare nella
propria sessione DM col peer. NON raggiunge il gateway del peer target.
Sintomo: il testo inviato "ritorna" come user message nella propria chat.

## Invio CROSS-PEER reale

POST al gateway del **peer target**, con `from_peer` nel body:

```
curl -X POST http://<target-ip>:18643/hmp/send \
  -H 'Content-Type: application/json' \
  -d '{"from_peer":"peer70","session_id":"peer141","text":"..."}'
→ {"accepted": true, "message_id": "hmp_...", "status": "queued"}
```

- `extract_peer(body)` risolve `from` → `from_peer` → `peer` → `sender` → `unknown`
  (core.py). Mettere la PROPRIA identità = corretto, non spoofing.
- `session_id` = chat del target (chat_id=session_id, altrimenti from_peer).
- **Sempre** verificare prima `/hmp/health` sul target (ritorna `node_id`).

## Pattern requester per e2e mesh

1. health check target (`/hmp/health` → node_id atteso)
2. POST `/hmp/send` con `from_peer` proprio + messaggio che innesca la catena
   voluta sul target (es. richiesta che il retriever matcha + tool call reale)
3. **catturare `message_id`** e usarlo come cross-check: l'esecutore deve
   citare l'exact message_id nella sua evidence → prova che l'identità
   requester è arrivata corretta (niente simulazioni)
4. `/hmp/poll/{message_id}` per lo stato async; `/hmp/send_and_wait` per la
   variante sincrona (polling interno, timeout)
