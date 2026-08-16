# Phase 0 Closure Review — peer141↔peer70 (2026-08-16)

**Coorte:** `dep-v250-phase0-p141p70-20260816T100844Z` · label `phase0_p141_p70`
**Scope amendment:** vaut note `fatti/phase0-scope-amendment-20260816.md`
**Reviewer delle label:** Fausto (umano, indipendente)

---

## Domanda 1 — La vertical slice runtime è affidabile?

**SÌ.**

| Evidenza | Esito |
|---|---|
| Hook conformance suite | 15/15 |
| Unit test suite | 120/120 (incl. 3 nuovi P9 collector) |
| Pinned-runtime smoke dispatch reale (peer141 0.20.1) | PASS — dispatch → sink interno → tool.considered → 🔍, single-fire |
| Pinned-runtime smoke dispatch reale (peer70 0.17.0) | PASS — idem (path sequential) |
| Catena reale request→pre_tool_call→retrieval→observe→feedback_sink→tool.considered→dispatch | dimostrata nei 3 casi, nessuno shortcut sintetico |
| collector_peer_id propagation | fixato e verificato nei trace reali (peer70 su entrambi i nodi) |
| version/base/hash fail-closed | `apply-core-patch.sh --check` exit 0 su entrambi |

## Domanda 2 — L'holdout è etichettato indipendentemente e pulito?

**SÌ.** 3 record, tutti `formal_holdout_eligible=True`, etichettati da Fausto
(append-only ledger, persistenza verificata): ACCEPT×2 (A, A-rev) +
REJECT×1 (B). Provenance organic_peer/organic_live, identità complete
(requester/processing/target/collector) su ogni trace.

## Domanda 3 — Threshold/margine soddisfano i criteri concordati?

**SÌ.** Threshold 0.65, margine 0.05 (Gate 4: precisione holdout ≥85%,
zero false-match read-only↔mutating):

- A: score 0.6847, margine 0.6847 → ACCEPT ✅
- A-rev: score 0.6751, margine 0.6751 → ACCEPT ✅
- B: score 0.6558 ≥ threshold ma composito mutating → REJECT partial_coverage,
  dispatch=none (zero falso positivo) ✅

**Precisione holdout: 3/3 = 100%** (≥ 85% richiesto).

## Domanda 4 — I record sintetici sono esclusi?

**SÌ.** La coorte `phase0_p141_p70` contiene SOLO i 3 casi organici reali
(envelope HMP reali tra peer141 e peer70). Traffico v2.4.6/v2.4.16,
acceptance, calibration, registry-sync e test è escluso dalla coorte e
dall'holdout (cohort_label e deployment_id diversi).

---

## VERDETTO: Phase 0 può chiudere ✅

**Fuori scope Phase 0 (invariati):** nuova sintesi capability, hmp-send,
esecuzione mutating, fleet rollout.
