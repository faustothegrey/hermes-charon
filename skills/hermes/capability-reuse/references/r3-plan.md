# Phase 1a Operational Plan — Passive Evidence Collection & Threshold Recalibration

**Version:** 1.2 (amended per reviewer decision 2026-08-16)
**Date:** 2026-08-16
**Author:** peer141 (implementation) with peer70 (coordination) concurrence
**Status:** ACCEPTED WITH REQUIRED AMENDMENTS — implementation may begin
**Reviewer verdicts:** v1.0 CONDITIONAL ACCEPT (3 P0 corrections) · v1.1
architecture ACCEPTED WITH REQUIRED AMENDMENTS (2 amendments below) ·
**v2.6.0 package REJECT / REBUILD (2026-08-16): Phase 0 closure NOT accepted;
engineering delta CONDITIONAL ACCEPT; remediation P0-1..P0-11 required.**

**Supersedes:** nothing — Phase 0 engineering vertical slice is PASS;
**Formal empirical Phase 0 closure: NOT YET** (v2.6.0 closure attempt
REJECTED 2026-08-16). This plan is the work that closes the empirical part.

---

## 0. Revision log

| # | Change | Rationale |
|---|---|---|
| P0-1 | Holdout sealed; sweep runs on TUNING only; holdout evaluated exactly once | Tuning on holdout destroys it; G4/G5 judged on a single sealed evaluation |
| P0-2 | `operator_seeded` excluded from the formal organic holdout; three separate provenance streams | Seeding cannot manufacture organic evidence; coherence with prior evidence policy |
| P0-3 | G6 demoted from closure gate to observed-result report (organic-only, cross-session) | Recurrence must be observed, not manufactured; no pressure to "produce" clusters |
| R1 | **Manual solicitation is NOT organic_live.** New provenance class `operator_solicited`; solicited manual workloads → tuning/challenge only, never G1 | Occurrence caused by the data-collection protocol ⇒ not organic, even if real and manual |
| R2 | **G1 = 60 retained.** Wilson CI reported (mandatory) but NOT used as stopping criterion this iteration | CI depends on accepted-positive count, class balance, abstention; repeated checking = sequential stopping problem; insufficient empirical info to design a defensible rule now |
| — | **Consumer_loop classification fix is a Phase 1a P0 blocker** (engineering): explicit provenance metadata, fail closed | `from_peer present → organic_peer` is insufficient; mislabeling would contaminate the holdout |

**Guiding principles (reviewer):** *Tune on tuning. Judge on holdout. Seed can
challenge the model, but it cannot manufacture organic evidence.* · *The
formal organic holdout must contain activity whose operational reason exists
independently of the experiment.*

---

## 1. Objective

Build an **independently labeled organic dataset** (Dataset B + C, per the
external review's remediation plan) large enough to recalibrate the retriever
threshold/minimum-margin on a **true tuning/holdout split**, closing the two
remaining empirical Phase 0 gaps (dataset scale and threshold calibration)
under the same rigor the external reviewer required:

- no synthetic holdout closure claims;
- no circular labels;
- no proxy precision (evaluate the real retriever, not a regex proxy);
- no simulated conformance (real pinned runtime only);
- gates predeclared **before** labeling starts;
- **tune on tuning, judge on holdout** (P0-1);
- **seed challenges the model but cannot manufacture organic evidence** (P0-2).

**Scope caveat (explicit, for the closure report):** with a 3-capability
registry and only `hmp-healthcheck@1.0.0` trusted, Phase 1a calibrates the
current retriever/registry's ability to discriminate when
`hmp-healthcheck@1.0.0` is a reusable match and when it must abstain. It does
**not** calibrate general multi-capability ranking; minimum-margin evidence
will be limited until semantically competing trusted capabilities exist. A
Phase 1a PASS must not be turned into a claim about multi-capability ranking
quality.

Phase 1a is **collection and calibration only**. No new capabilities, no
catalog expansion, no synthesis, no active rollout, no fleet changes. Phase 1a
is strictly separated from Phase 1B.

## 2. Current state (measured 2026-08-16)

| Item | Value |
|---|---|
| Phase 0 status | engineering vertical slice: PASS · **Formal empirical closure: NOT YET** (v2.6.0 attempt REJECTED) |
| Runtime mode | shadow on peer141 + peer70 (post-Phase-0 baseline) |
| Active-mode drop-ins | removed from activation path; preserved as artifacts in `evidence/rejected-phase0-closure-2026-08-16/dropins/` |
| Registry | 3 capabilities; only `hmp-healthcheck@1.0.0` trusted |
| Retriever | text-matching (token+bigram), no embeddings |
| Current thresholds | intervention 0.65, min margin 0.05 — **engineering defaults, NOT calibrated** |
| Organic traffic rate | ~4 organic_peer events/week (measured) |
| Total retrieval events (peer70 log) | 63 (2026-08-15: 19, 2026-08-16: 44, most test/Phase-0 traffic) |
| Recurrence evidence | 4 independent occurrences, 2× hmp-healthcheck |
| Passive pipeline (peer70) | analyzer + dashboard + central-collector cron every 15 min; `capreuse-central/` currently empty (collector path needs verification) |
| Passive pipeline (peer141) | **missing** — no analyzer/collector/dashboard scripts, no cron |

## 3. Scope

### In scope
1. **Passive pipeline parity** — install analyzer + dashboard (+ collector
   agent) on peer141; verify central-collector on peer70 actually produces
   `capreuse-central/` output; both peers emit `retrieval_event` from the
   live hook path with schema 1.3, cohort `phase0_p141_p70`, provenance
   streams separated.
2. **Dataset C acquisition** — real hook-visible requests. **Provenance
   streams, never mixed (P0-2, R1):**
   - `organic_live` — spontaneous operator/peer traffic whose operational
     reason exists **independently of the experiment** → **may enter the
     formal organic holdout** (G1);
   - `operator_solicited` — manual workloads solicited by the Phase 1a
     protocol (e.g. a reminder asking Fausto to perform real operations):
     real, manual, operationally realistic, but their occurrence is caused
     by the data-collection protocol → **tuning/challenge/failure discovery
     only; NEVER counted toward G1**;
   - `operator_seeded` — realistic prompts authored for the protocol →
     **tuning / challenge / boundary testing only; NEVER organic holdout**;
   - `scheduled_protocol` / `cron` / `calibration` — scheduled watchdog and
     protocol traffic → **tuning / challenge + G9 pipeline health; NEVER
     formal holdout**;
   - `unknown` / missing provenance → **excluded; `formal_holdout_eligible`
     = false (fail closed)**.
3. **Dataset B acquisition** — post-execution request/outcome pairs from the
   same streams (provenance preserved).
4. **Blind human labeling workflow (G2)** — Fausto labels from the reviewer
   queue; ACCEPT/REJECT/UNSURE + reason code; append-only ledger; budget
   ≤15/week; labels durable across queue regeneration (verified). **Blind
   rules:** the labeler never sees `top_score`, chosen threshold/margin,
   retriever decision, or predicted label — only the redacted request,
   capability contract, and execution preview. UNSURE is correct and
   preserved.
5. **Grouped tuning/holdout split (G3, P0-1)** — frozen; grouping unit is
   template/base-prompt/task-family/session relationship, not individual
   rows. Paraphrases of the same task stay in the same side of the split.
   Zero template overlap; no `variant N`; no repeated base prompts.
6. **Threshold/margin recalibration on TUNING ONLY (P0-1)** — sweep
   threshold 0.30–0.85 × margin 0.00–0.15 on the tuning set; select
   operating point; freeze it. The holdout is **sealed** and evaluated
   **exactly once** for G4/G5. If G4/G5 fail, Phase 1a fails and a new
   calibration cycle/version opens — no re-tuning against the holdout.
7. **Recurrence analysis as observed result (P0-3)** — report completed with
   provenance separated, deduped by session/template/task-family; report
   "number of qualifying organic clusters = N" without requiring N ≥ 3 to
   close calibration. If recurrence discovery becomes a formal Phase 1a
   objective later, the gate must require: cluster counts from
   `organic_live` only, occurrences spanning ≥ N distinct sessions, and no
   repeated seeded/template instances counted — **cross-session evidence,
   not "≥5 per session".**

### Out of scope (Phase 1a)
- New capability registration / catalog expansion.
- hmp-send or any mutating capability activation.
- Synthesis / proposal generation.
- Fleet rollout to peer84/128/138/106/58.
- Embeddings or retriever architecture change (only if dataset shows
  text-matching cannot reach the gate — then a separate plan).
- Any Phase 1B activity (new trusted capabilities, active dispatch).

## 4. Gates (predeclared — fixed before labeling)

| Gate | Criterion |
|---|---|
| **G0 Pre-seal engineering (reviewer 2026-08-16)** | Required BEFORE any `formal_holdout_eligible` record may start accumulating: (a) **reviewed HMP adapter source/hash** provided as separate release surface (P0-8); (b) **request-unique trace_id proven on live HMP** — chat_id/peer fallback no longer acceptable for holdout records (P0-10); (c) exact Phase 1a cohort label configured (`CAPABILITY_REUSE_EXPECTED_COHORT_LABEL=phase0_p141_p70`); (d) UTC deployment boundary verified (deployment_timestamp == UTC now, no local-time-with-Z). |
| G1 Dataset C size (organic) | ≥ 60 independently labeled `organic_live` pairs in the sealed holdout. `operator_solicited`/`operator_seeded`/`scheduled_protocol` do NOT count toward G1. |
| G2 Label independence | blind human labeling by Fausto (no score/threshold/decision/predicted-label visibility); ledger append-only; no label generated by the pipeline; UNSURE preserved |
| G2b Provenance fail-closed | traffic classification uses explicit provenance metadata; `from_peer` alone never implies `organic_peer`; missing/ambiguous provenance → `unknown` → `formal_holdout_eligible=false` (P0 engineering blocker) |
| G3 Split integrity | grouped split frozen by template/task-family/session; zero template overlap; zero repeated base prompts; provenance recorded per pair; manifests + hashes frozen |
| G4 Holdout precision | top-1 precision ≥ 85% on the sealed holdout, single evaluation (TP/(TP+FP) as defined in §4.1); 95% CI reported in the closure report (CI mandatory in report, not necessarily a gate) |
| G5 False-match | zero false matches across effect classes (read-only↔mutating tolerance zero) |
| G6 Recurrence (report, not gate) | recurrence analysis completed; organic/operator_seeded provenance separated; deduped by session/template/task-family; "qualifying organic clusters = N" reported (N ≥ 3 NOT required for closure) |
| G7 Latency | defined benchmark (see §4.2): p50 ≤ 100 ms, p95 ≤ 200 ms on pinned runtime |
| G8 Calibration record | threshold/margin sweep on TUNING ONLY; chosen operating point reported with margin distribution + abstention rate, not a single point estimate |
| G9 Pipeline health | both peers: analyzer runs, dashboard refreshes, central collection non-empty, zero unclassified events in the clean cohort |
| G10 Evidence packaging | all raw evidence under `evidence/phase1a-*` with SHA256SUMS + manifest, per `phase0-closure-playbook.md` pattern |

### 4.1 G4 metric definition (mathematical)

- TP = retriever accepts ∧ human labels eligible/exact-match
- FP = retriever accepts ∧ human rejects
- FN = retriever abstains/rejects ∧ human labels eligible/exact-match
- TN = retriever abstains/rejects ∧ human rejects

Report: precision `TP/(TP+FP)`, recall `TP/(TP+FN)`, confusion matrix,
abstention rate, and **95% CI** (Wilson or exact binomial) — CI mandatory in
the report.

### 4.2 G7 latency benchmark definition

Measure: **hook → retrieval decision** wall-clock (retriever only, from hook
entry to decision return). Report separately: registry load included or warm
cache; warm vs cold cache; sample count (≥ 100 runs); environment (pinned
runtime, same node, same core). Without these, p50/p95 are not reproducible.

## 5. Work sequence

1. **Pipeline parity (week 1)** — copy analyzer/dashboard/collector scripts
   to peer141 (from peer70 / skill `scripts/` source), configure cron every
   15 min.
2. **Pipeline-health smoke (week 1)** — verify peer70 central-collector
   output (`capreuse-central/` currently empty → investigate, fix, verify a
   full cycle); one organic request per peer → fresh `retrieval_event` →
   analyzer delta in `latest.json` → dashboard refreshed. Gate G9 preflight.
3. **7-day organic-rate measurement (week 1–2)** — measure real
   `organic_live` rate.
4. **Freeze labeling protocol + blind-label rules (week 2)** — Fausto
   reviews queue weekly (≤15/week); blind rules per G2; UNSURE allowed;
   labels survive regeneration.
5. **Start organic collection** — continuous `organic_live` capture.
6. **Add `operator_seeded` challenge/tuning data if useful** — provenance
   rigorously separated; used for tuning/challenge/boundary testing only;
   never counted as organic holdout evidence (P0-2).
7. **Reach predeclared dataset sufficiency** — G1 floor (60 organic pairs)
   on the organic stream.
8. **Group/deduplicate** — dedupe by session/template/task-family; prepare
   grouped units.
9. **Freeze tuning/holdout manifests + hashes** — grouped split (G3);
   manifests + SHA256SUMS frozen.
10. **UNSEAL TUNING ONLY** — sweep threshold 0.30–0.85 × margin 0.00–0.15;
    select configuration; freeze it.
11. **UNSEAL HOLDOUT ONCE** — single evaluation: compute G4/G5 + CI +
    confusion matrix + abstention rate.
12. **Recurrence report** — separate organic analysis (P0-3): provenance
    separated, cross-session, "qualifying organic clusters = N".
13. **Evidence manifest + SHA256SUMS** — package under `evidence/phase1a-*`.
14. **Phase 1a closure review** — map every gate to evidence; submit to
    external reviewer.

## 6. Timeline estimate

| Track | Duration | Notes |
|---|---|---|
| Pipeline parity + health smoke | 1 week | — |
| **Tuning/challenge readiness** | **potentially 2–3 weeks** | via operator-solicited + scheduled + seeded data |
| **Formal G1 completion** | **~15 weeks lower bound at current ~4 eligible organic_live/week** | determined EXCLUSIVELY by spontaneous organic_live accumulation; before UNSURE/exclusions |

**Critical-path note (R1, reviewer):** manual solicitation and scheduled
traffic do NOT accelerate G1. The correct schedule statement is:

- Tuning/challenge readiness: potentially 2–3 weeks with
  operator-solicited + scheduled data.
- Formal G1 completion: determined exclusively by spontaneous organic_live
  accumulation. At the currently observed ~4 eligible events/week, the
  nominal lower bound remains ~15 weeks for N=60, before UNSURE/exclusions.

The two-track architecture means tuning/calibration work can proceed in
parallel while organic_live accumulates independently.

## 7. Roles

| Role | Actor | Responsibility |
|---|---|---|
| Labeling (blind) | Fausto (human, independent) | blind labels, UNSURE, split freeze approval |
| Coordination | peer70 | canonical state, collector, review orchestration |
| Implementation | peer141 | pipeline, scripts, recalibration, evidence |
| Reviewer | external | gate approval, closure acceptance |

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Organic traffic too low (measured ~4/week) | accept the ~15-week lower bound for G1; `operator_seeded` only improves tuning-set quality, never organic holdout volume |
| Tuning on holdout (methodology) | P0-1: holdout sealed; single evaluation; failure opens a new calibration cycle |
| Seeded data mislabeled as organic | three provenance streams, never mixed; G3 programmatic overlap check; closure report states organic count explicitly |
| Label anchoring | G2 blind rules; labeler never sees scores/thresholds/decisions/predicted labels |
| Label fatigue / budget | ≤15/week cap, UNSURE path, queue prioritization |
| Pipeline silent failure (collector empty today) | G9 health gate + weekly dashboard check |
| Threshold overfit / small-sample precision | G8 margin distribution + G4 95% CI mandatory in report; floor 60 pairs; no claim beyond criterion |
| Recurrence pressure ("produce clusters") | G6 as observed result only; organic-only, cross-session, provenance separated |
| Scope creep toward Phase 1B/2 | explicit out-of-scope section; closure requires reviewer sign-off; Phase 1a strictly separated from Phase 1B |

## 9. Definition of done (Phase 1a closure)

- G1–G10 all PASS with evidence (G6 as completed report; G4 CI reported).
- Recalibrated threshold/margin recorded in canonical state (with the caveat:
  calibrated on this dataset for `hmp-healthcheck@1.0.0` discrimination, not
  production-generalizable, not multi-capability ranking).
- Passive pipeline running on both peers, dashboards current.
- Closure report packaged and submitted for external review.

---

*Draft for external review (v1.1, revised per reviewer conditional-accept
feedback). Companion notes: `phase0-review-methodology-lessons.md`,
`phase0-empirical-remediation-plan.md`, `phase0-closure-playbook.md`.*
