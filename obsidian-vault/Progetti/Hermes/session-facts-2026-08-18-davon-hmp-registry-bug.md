# Session Facts — 2026-08-18 (Davon HMP, registry timestamp, bug HMP)

> Sessione del 18/08. Vault per il dettaglio, hot per i puntatori (skill memory-vault-hybrid).

## 1. peer136 / Davon — da nodo Telegram a nodo Hermes HMP completo

- Davon = Debian 13 (trixie) aarch64, user fausto, Hermes **0.20.2**, hostname "Davon" (peer136 aveva hostname "Diet" — corretto su indicazione di Fausto).
- **Modello cambiato**: `gpt-5.6-luna`/openai-codex → **`deepseek/deepseek-v4-flash`** / nous / inference-api (config.yaml, backup creato).
- **Trixie rimosso**: `trixie-hmp.service` (systemd, "Trixie Pi Agent" — hmp-server.py custom, AGENT pi.dev v0.80.10) occupava :18643. Stop + disable + watchdog cron (`trixie-watchdog.sh` ogni 5 min) rimosso.
- **Plugin hmp v0.1.5** installato dal peer (più recente del 0.1.4 del mesh).
- **Patch core G0/G2b applicate sul 0.20.2** (il core era vanilla → "consumer loop error"): 6 file, 10 punti:
  1. `gateway/platforms/base.py` — MessageEvent: `trace_id` + `capability_reuse_context` (pattern: dopo `message_id`, prima del commento Platform-specific)
  2. `run_agent.py` — AIAgent forwarder: params + forward
  3. `agent/agent_init.py` — init_agent: params + `agent._trace_id` + `agent._capability_reuse_context`
  4. `agent/turn_context.py` — kwargs pre_llm_call: trace_id + provenance + marker
  5. `gateway/run.py` — firma `_run_agent`/`_run_agent_inner`, 2 chiamate inner (multiplex off + profile scope), AIAgent creation, entry-point (19700), pending-drain (29104), cache-refresh
  6. `gateway/turn_context.py` — TurnContext: campi `trace_id` + `capability_reuse_context`
- **Bug 0.20.2 specifici risolti durante l'adattamento**:
  - `NameError: trace_id` nel cache-refresh: su 0.20.2 il blocco cache/AIAgent vive in `run_sync`/TurnContext (non in `_run_agent_inner`) → aggiunti campi al TurnContext, usati `ctx.trace_id`
  - doppio `trace_id=` nella chiamata profile-scope (patch sovrapposte) → deduplicato
- **node_id era copiato da Stella**: `peer141` → corretto a `peer136` (config `platforms.hmp.extra.node_id`)
- **Verifica finale**: HMP health `node_id: peer136`, messaggio test → "Sono Hermes Agent (Nous Research), modello deepseek-v4-flash su provider nous" ✅

## 2. Confronto skill-vs-runtime capability-reuse (peer136 nota)

- peer136 aveva riportato (17/08): "plugin 2.5.0 (peer70's runtime), skill 2.6.0" — lettura SHA-verified all'atto della copia.
- Verifica peer70 (18/08): plugin e skill entrambe **2.6.0**, hash `v244_metadata.py` = `9ddfcfe3e049ddff...` **identico** su entrambi i nodi. La 2.5.0 era uno stato temporale del 17/08, superato.
- **Lezione**: versioni senza timestamp sono ambigue → aggiunto `version_checked_at` nel registry (manifests) + punto 3a nella skill hermes-hmp (mtime + sha256, mai md5).

## 3. Registry timestamping

- `~/.hermes/registry/peers/peer70.json`: ogni skill ha ora `version_checked_at` (8 skill).
- `registry.json`: `version_checked_at` per peer70 + `updated_at` indice.
- Task a peer136 (via HMP): aggiornato `capability-reuse` da **2.2.0 → 2.6.0** in skills[] e plugins[] del manifest peer70 (backup `/tmp/peer70.json.bak`). Verifica indipendente fatta da Charon: ✅ 2.6.0 in entrambe le sezioni.

## 4. BUG HMP — messaggio orfano in delivering (da analizzare)

- **Sintomo**: messaggio resta in `delivering` per sempre.
- **Causa**: riavvio del gateway a metà turno → il consumer non riprende il messaggio.
- **Effetto**: la sessione del messaggio resta bloccata (nuovi messaggi sulla stessa sessione non processati), ma sessioni diverse funzionano (ping PONG ok).
- **Workaround**: re-invio con nuovo message_id.
- **Pulizia**: messaggio orfano marcato `failed` con `error='orphaned_delivering_after_gateway_restart_20260818'` nel DB di peer136.
- **Fix potenziale da analizzare**: recovery dei `delivering` orfani al boot del gateway, o timeout di stato.

## 5. Verdetto reviewer (email Libero, ID 6, 17/08) — per peer128

- Contenuto: "G0 e G2b CLOSED, remediation completata su entrambi i core, bundle pronto per sealed Phase 1a organic holdout, subordinato a decisione GO del reviewer. Nota: validation/solicitation esplicitamente non-organic; organic_live mai per traffico creato per raccogliere evidence."
- **File**: `~/.hermes/data/peer128-pending-verdict.md` — **NON consegnare automaticamente** (istruzione Fausto 18/08: solo su richiesta esplicita).

## 6. Policy aggiornata (18/08)

- **peer70 = coordinatore di tutti i peer** (Fausto: "tu sei già il coordinatore, ed è già tanto").
- **peer70 NON sviluppa capability-reuse** — lead dev = peer128 (direzione, gate, release); peer141 = impl+QA.
- peer70 continua: orchestrazione, GO/NO-GO fasi, review.

## 7. Stato mesh (18/08)

| Peer | IP | Host | Hermes | HMP | Modello |
|---|---|---|---|---|---|
| peer70 | .70 | Charon | 0.17.0 | ✅ | deepseek-v4-flash |
| peer58 | .58 | Sidecar | 0.19.0 | ✅ | (default) |
| peer106 | .106 | Trixie | 0.20.2 | ✅ | (default) |
| peer128 | .112 | MacPro | — | ❌ OFFLINE | — |
| peer136 | .136 | Davon | 0.20.2 | ✅ | deepseek-v4-flash |
| peer138 | .138 | DietPi | 0.19.0 | ✅ | deepseek-v4-flash |
| peer141 | .141 | Stella | 0.20.1 | ✅ | deepseek-v4-flash |

- peer105 RIMOSSO permanentemente (17/08) da registry + script + cron (YouTube dispatch → peer106).
- peer84 offline (finestre cooling).

## 8. System health (18/08 11:45)

- Undervoltage: `throttled=0x0` — nessun problema. Watchdog ogni 15m ok.
- Uptime 7d, load 0.6, disk 26%.
- Memoria hot consolidata (2,164/2,200, poi compattata a 2,042 — 92%) con skill memory-vault-hybrid.
- Watchdog cron in pausa dal 02/08: peer70-watchdog, HMP bloccati, dsi-error, session-70pct — da decidere se riattivare.
