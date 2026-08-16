# G0 Report — HMP adapter post-fix + request-unique trace_id

**Data:** 2026-08-16 · **Executor:** Charon (peer70, Hermes 0.17.0) · **Stato:** DONE (shadow)

## Contesto

capability-reuse 2.6.0 = ACCEPT. G0 pre-seal fuori skill: P0-8 (adapter.py non source-reviewed) e P0-10 (consumer_loop usava chat_id/peer come trace_id).

## Modifiche (adapter.py v0.1.4-g0)

1. **`_process_item()`** — logica estratta dal consumer_loop, testabile e con safety net (un messaggio rotto non uccide il loop).
2. **trace_id = `uuid.uuid4()`** per richiesta (P0-10): generato una volta, propagato a retrieval → surface_start → surface_complete. Nessun fallback chat_id/peer/session per record eleggibili.
3. **`_classify_traffic()`** — classificazione provenance fail-closed estratta (fix 2.6.0 preservato, 12+ casi).
4. **`_extract_collector()`** — collector_peer_id: body > env > absent (envelope v2.4.18 preservata).
5. Bug fix: surface_execution_complete usava `trace_id=chat_id` invece della variabile → ora stesso UUID della catena.

## Test

- Suite: `analysis/test_g0_adapter.py` — **30/30 PASS** (Charon 0.17.0)
- 2 richieste → trace_id diversi ✅ · stessa richiesta → stesso trace in catena ✅ · 14 casi fail-closed ✅ · collector body/env/absent ✅ · nessun record con chat_id/peer come trace ✅

## Smoke live

| # | trace_id | traffic | catena nel log |
|---|---|---|---|
| 1 | `996b6f1b-c067-4c63-bfc6-5deedbb694c8` | organic_peer | retrieval→start→complete ✅ |
| 2 | `5577b9d5-9a15-4e80-a662-bf6fe3fb2034` | registry_sync | retrieval→start→complete ✅ |

## Artefatti

- `adapter.py` — SHA-256 `c164ba7a498410c93447da9c16b4e70eae9450c97389f7217d75102ec3eafd22`
- `manifest.json` — artifact, version, sha, compat core, status shadow
- Bundle: `~/.hermes/g0-bundle/` (adapter.py + manifest.json) — senza patches/, senza segreti

## Note

- Compatibilità dual-core: nessuna patch core; adapter usa API stabili comuni a 0.17.0 e 0.20.1 (verifica su peer141 0.20.1 da fare con accordo Fausto).
- Resta shadow: nessun active rollout. Il gateway attivo (systemd) carica il codice al prossimo riavvio manuale.
