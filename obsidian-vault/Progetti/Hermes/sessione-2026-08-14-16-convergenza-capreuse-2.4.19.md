# Sessione 2026-08-14/16 — Convergenza capability-reuse 2.4.19 + fix HMP

## Contesto
- Ripresa da sessione precedente (bug cron kill-gateway → restart loop, risolto)
- Obiettivo: allineare la rete su capability-reuse 2.4.18→2.4.19, gestione patch core per-version, fix bug HMP

## 1. Gateway & cron
- Bug cron 'once' con run_at passato → gira a OGNI tick → job kill-gateway → restart loop infinito (14/08)
- Rimossi job `2793e9c396c5` (restart-gateway-harness-feedback) e `20ed1557cd17` (kill -9 vecchio)
- **Regola: restart gateway = SEMPRE manuale da shell esterna** (guardiano blocca in-band)

## 2. Fix typing Telegram (bug #48678)
- **Causa**: custom bubble 🔍 (tool.considered) emette un evento per tool call → progress consumer ri-arma il timer typing di Telegram (~5s) dopo OGNI bubble, anche l'ultima del turno → bubble "typing" resta per minuti
- **Fix** (commit `5bb34a7`): guard in `gateway/run.py` — ri-armare typing solo se `progress_queue` non è vuota (`_run_still_current() and not progress_queue.empty()`), in entrambi i call-site
- **Lezione**: Telegram non ha API stop-typing — chi aggiunge progress events per tool call deve gateare il re-arm su "more events queued"

## 3. Capability-reuse 2.4.19 (convergenza completa 15/08)
- Skill+plugin **2.4.19** allineati su peer70/141 (e2e **10/10**: Case A, A-reversed, B)
- **Core patch per-version management** (sezione skill 2.4.19):
  - `patches/` NON viaggia nel sync skill (validator rifiuta)
  - Patch vivono in `~/.hermes/patches-core/` per versione core:
    - `core-0.17.0-observe.patch` (peer70, sha `fa607b51`, = commit `00b1115`+`5bb34a7`+`38d8162`)
    - `core-0.20.1-observe.patch` (peer141, commit `6b9916d`)
  - Script `apply-core-patch.sh` v0.17.1: `--check` (0=applied, 2=ready, 3=conflict), `--smoke` (funzionale stringa+dict), `--gate` (check+smoke, exit!=0 bloccante)
- **Canale observe 🔍**: hook `pre_tool_call` → `{"action":"observe","feedback":...}` → feedback_sink (single-fire) → `tool.considered` → bubble 🔍
  - Formati: stringa (legacy) + dict `{"kind","text","duration_ms"}` (emoji per kind, cap 40)
  - peer141 lo ha implementato internamente sul suo core 0.20.1 (plugins.py:5815/5868, tool_executor.py:545/569, run.py:3953)
- **Harness-feedback plugin**: v0.1.1 dict (era 0.1.0 string-only), dummy per test
- **Pitfall**: `.bak*` in `plugins/` o `skills/` SHADOWA la discovery → il gateway carica la versione vecchia. Backup SOLO in `~/.hermes/backups/`

## 4. Driver dispatch-proof v2.5.0
- `observe-channel-real-gateway-dispatch-proof.py`: attraversa dispatch REALE → hook → sink interno → tool.considered → bubble reale
- **FAIL iniziale su peer70**: single-fire "violato" ma era il plugin dummy harness-feedback (kind=generic) — il retriever rispettava il single-fire
- **Fix**: driver conta SOLO `kind=retrieval` (ignora kind=generic), robusto a rinomina plugin
- peer141 ha applicato il fix + syncato; PASS su entrambi i nodi

## 5. HMP — regola forte lettura messaggi (16/08)
- **Problema**: il log gateway tronca la preview a 80 chars (`_msg_preview[:80]`) e NON ha il message_id → falsi "troncamenti" (messaggi in realtà integri nel DB)
- **REGOLA FORTE**: leggere messaggi HMP SEMPRE dal DB `~/.hermes/data/hmp_gateway_plugin/messages.db` (campo `text`), MAI dal log
- **Helper**: `~/.hermes/scripts/hmp-read-msg.py` (`<message_id>`, `--last [peer]`, `--from <peer> [N]`)
- Distribuito su peer70/58/138/141 (script + SKILL.md hermes-hmp con regola in cima + reference `hmp-read-messages-from-db-2026-08-16.md`)
- DB messaggi HMP reale: `data/hmp_gateway_plugin/messages.db` (NON `data/hmp/agent_messages.db` che è del dual-plane defunto)

## 6. Rete & peer
- **peer106 (Trixie)**: OFFLINE da 14/08 fino a nuovo avviso — upgrade Hermes (0.15.1) e HMP (0.1.3→0.1.4) pendenti
- **peer141 (Stella)**: Hermes 0.20.1, hmp 0.1.4, canale observe interno, sviluppa per conto proprio
- **peer138 (DietPi)**: gateway systemd DI SISTEMA (no --user), hmp 0.1.4
- **peer70 (Charon)**: Hermes 0.17.0 + 4 commit locali (observe plumbing + typing fix + dict port)
- HMP 0.1.4 su tutti i peer attivi; dual-plane :18644 ritirato
- **Policy operativa**: peer70 = orchestratore/source of truth, massima stabilità — niente patch core sperimentali su peer70; sviluppo su peer141

## 7. Backup
- Nightly backup GitHub riattivato (era paused dal 02/08): job `5847db0f5cb7`, 0 23 * * *, repo `faustothegrey/hermes-charon`
- Backup manuale eseguito 15:19 (push OK `106c3c1..6fe0181`)
- Bundle secrets sano (9.8 KB — niente state.db)

## Stato finale
- Convergenza 2.4.19 completa, gate PASS, e2e 10/10, regola lettura DB attiva
- In sospeso: peer106 upgrade, porting bubble su peer58/138 (opzionale)
