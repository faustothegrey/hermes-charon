# Phase 0 — Scope Amendment: coorte di validazione peer141 ↔ peer70 (2026-08-16)

> Fatti persistenti — la memoria hot contiene solo il puntatore a questa nota.
> Relativa a capability-reuse ([[capability-reuse-v250]]).

## Amendment esplicito

**La coorte prevista peer58 ↔ peer106 per la validazione Phase 0 è SOSTITUITA,
per la sola validazione, da peer141 ↔ peer70.**

Motivo: i peer originari non sono disponibili — peer106 OFFLINE, peer58 solo
target e2e senza patch observe. peer141 (0.20.1) e peer70/Charon (0.17.0)
hanno entrambi: skill capability-reuse v2.5.0, patchset observe v0.3.0, core
patch per-version, e REAL-GATEWAY DISPATCH PROOF già PASS su entrambi i core.

**Natura giuridica:** SCOPE AMENDMENT per la validazione Phase 0. Lo stato
canonico (t6-scope-statement, [[capability-reuse-v2419]]) CONTINUA a nominare
peer58↔peer106 come coorte formale; questo documento registra la sostituzione
temporanea e la motiva. Nessuna generalizzazione alla fleet (peer84, peer128,
peer138, ecc.) — regola T6 invariata.

## Casi funzionali (semantica canonica A/B preservata)

- **A**: peer141 → check HMP health per peer70 (dispatch capability allowlistata hmp-healthcheck@1.0.0)
- **A reversed**: peer70 → check HMP health per peer141 (anti-hardcoding identità)
- **B**: peer141 → check health peer70 e riavvialo se unhealthy (retrieval del candidato + REJECT per partial coverage/effect mismatch, dispatch=none)

## Identità da auditare in ogni trace

`requester_peer_id` · `processing_peer_id` · `target_peer_id` · `collector_peer_id`
— MAI confondere i ruoli di peer70 (requester/processor/collector/relay).

## Critical path Phase 0

1. scope amendment (questa nota) ✅
2. readiness check peer141↔peer70 ✅ (HMP health OK entrambi i lati, 2026-08-16)
3. engineering fixes: Observe hardening · 1 decisione tool → 1 invocazione pre_tool_call · version/base/hash fail-closed · collector_peer_id propagation · verifica source/hash adapter HMP
4. pinned-runtime smoke su peer141/70 (catena request → pre_tool_call → retrieval → observe → feedback_sink → tool.considered → dispatch, niente shortcut sintetici)
5. casi A / A-reversed / B
6. test persistenza label umane (append → regenerate → stesso review_id → label persiste → supersede → ledger precedente intatto)
7. coorte pulita fresca, taggata `peer141↔peer70 Phase 0 cohort`, SOLO traffico organico (niente v2.4.6/v2.4.16/acceptance/calibration/registry-sync)
8. holdout etichettato indipendentemente (solo trace che passano l'eligibility envelope)
9. calibrazione threshold + margine minimo su holdout
10. closure review Phase 0 (vertical slice affidabile? holdout pulito? threshold ok? record sintetici esclusi?)

## Stato engineering (2026-08-16, peer141)

- ✅ **collector_peer_id propagation FIXATO**: `retriever.py` ora passa
  `collector_peer_id` (helper `_extract_collector`: hook_context →
  env `CAPABILITY_REUSE_COLLECTOR_PEER_ID` → "" mai inventato) e
  `hmp/adapter.py` idem. 3 nuovi test P9 (context/env/absent, 15/15 file,
  suite 120/120 PASS). Skill source e runtime syncati.
- ✅ **1 tool decision → 1 pre_tool_call**: driver
  `observe-channel-real-gateway-dispatch-proof.py` PASS fresco su peer141
  (2 tool call stesso turno → 1 sola bubble 🔍, sink interno reale).
- ✅ **version/base/hash fail-closed**: `apply-core-patch.sh --check` exit 0
  (base c896c09 antenato, sha 0e97fc8b ok, patch 0.3.0 applicata).
- ✅ **Adapter HMP source/hash**: runtime `plugins/hmp/` v0.1.4 è la source
  (skill hermes-hmp non contiene adapter.py separato); post-fix sha256
  adapter.py `24f1f554...`, core.py `abf0c550...`, __init__.py
  `06cda183...`; surface_execution_* presenti (v2.4.18).
- ⏳ **Pinned-runtime smoke su peer141+peer70**: prossimo passo — richiede
  propagazione fix a peer70 (skill/plugin sync + 1 riavvio manuale) poi
  casi A / A-rev / B.

## Casi Phase 0 — peer141↔peer70 (2026-08-16, REALI su gateway attivi)

Drop-in systemd `capreuse-active.conf` su entrambi i nodi:
`CAPABILITY_REUSE_MODE=active`, allowlist hmp-healthcheck,
`CAPABILITY_REUSE_PERMISSIONS=hmp.network.read`,
`CAPABILITY_REUSE_AVAILABLE_CAPABILITIES=hmp_client_installed`,
`CAPABILITY_REUSE_COLLECTOR_PEER_ID=peer70`. (Pitfall: senza permessi
dichiarati il retriever fa fail-closed — primo tentativo rejected con
`filter_rejection_reasons: Required permissions ['hmp.network.read']`.)

- ✅ **Caso A** (peer141 → "check HMP health for peer70", envelope reale
  `hmp_ef18baf3a7404cd0`): retrieval attivo hmp-healthcheck@1.0.0 score
  0.6847, eligibility=accepted, dispatch=pending, intervened=True,
  intervention_event presente, risposta "peer70 HMP health OK". Identità:
  req=peer141, proc=peer70, tgt=peer70, coll=peer70.
- ✅ **A-reversed** (peer70 → "check HMP health for peer141", envelope
  `hmp_bb8889ab46e44962`): identità specchiate (req=peer70, proc=peer141,
  tgt=peer141, coll=peer70), accepted, dispatch=pending, intervened=True,
  risposta "HMP health peer141: OK".
- ✅ **Caso B** (peer141 → "check peer70 health and restart it if
  unhealthy", envelope `hmp_275224f118b44ccc`): retrieval del candidato
  hmp-healthcheck score 0.6558 poi REJECT `partial_coverage` (req_effect=
  mutating vs cap_effect=read_only, covered=False), **dispatch=none**,
  intervened=False, nessun restart. Risposta "peer70 = HEALTHY, no restart
  needed".
- 🔍 Bubble observe confermata in tutti i casi (catena dispatch reale →
  sink → tool.considered su entrambi i core, driver PASS pre-casi).
- ⏳ **Label persistence test** (append → regenerate → stesso review_id →
  supersede → ledger precedente intatto): prossimo passo.

## Coorte pulita + holdout (2026-08-16) — CHIUSO ✅

**Coorte:** `dep-v250-phase0-p141p70-20260816T100844Z`, label
`phase0_p141_p70` (cohort.json su entrambi i nodi). 3 casi formali ri-eseguiti
sotto la nuova coorte (envelope HMP reali): A `hmp_873ce54323c94921`,
A-rev `hmp_60c642f584ed4f3c`, B `hmp_f669896557244ce2`. Solo traffico
organic_peer, zero sintetico. Fix minore: `EXPECTED_COHORT_LABEL` ora
configurabile via env `CAPABILITY_REUSE_EXPECTED_COHORT_LABEL` (era
hardcoded v2.5.0_live) — review_queue.py syncato su entrambi i nodi.

**Review records (3, holdout-eligible True tutti):**
- peer70 `review_3575fab783ce5935b3bea500753ec038` — A: hmp-healthcheck,
  eligible_shadow_only, tgt peer70 → label umana **ACCEPT/exact_match**
- peer70 `review_41c0d0fb54af49e24bd46f94032604f0` — B: hard negative
  (ineligible_candidate_filter) → label umana **REJECT/partial_coverage**
- peer141 `review_96610188d34ebafdfbe2a292ae6cafac` — A-rev:
  eligible_shadow_only, tgt peer141 → label umana **ACCEPT/exact_match**

**Calibrazione threshold/margine su holdout (0.65 / 0.05):**
3/3 = 100%. B rifiutato per effetto (score 0.6558 ≥ thr ma composito
mutating → partial_coverage, dispatch=none) — nessun falso positivo
read-only↔mutating. Verdict PASS.

## Closure review Phase 0 — domande (2026-08-16)

Risposte (evidenza in
`skills/hermes/capability-reuse/evidence/phase0-closure-review-2026-08-16.md`):

1. **Vertical slice runtime affidabile?** SÌ — conformance 15/15, unit 120/120,
   smoke dispatch reale PASS su entrambi i core, catena completa nei 3 casi.
2. **Holdout etichettato indipendentemente e pulito?** SÌ — 3 record
   holdout-eligible, label Fausto append-only (ACCEPT×2 + REJECT×1),
   provenance organic_live, identità complete.
3. **Threshold/margine ok?** SÌ — precisione 3/3 = 100% (≥85%), zero
   false-match read-only↔mutating (B rifiutato nonostante score≥thr).
4. **Record sintetici esclusi?** SÌ — coorte solo organic_peer reale,
   acceptance/calibration/registry-sync/test fuori.

**VERDETTO: Phase 0 può chiudere ✅** — fuori scope: nuova sintesi capability,
hmp-send, esecuzione mutating, fleet rollout.

## Link

- [[capability-reuse-v250]] · [[observe-channel-patchset]] · [[peer-network]]
