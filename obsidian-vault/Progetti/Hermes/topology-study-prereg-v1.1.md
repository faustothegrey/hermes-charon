# Preregistration — Read-Only Skill-Topology Study (v1.1 — FROZEN)

**Project:** capability-reuse (spec v1.6) — Phase 1 gate
**Owner:** Fausto · **Executor:** Hermes · **Status:** frozen before data access (v1.1 supersedes v1.0; changelog at end)
**Deliverable:** one table, confidence intervals, one verdict. No production code.

## 1. Question

Does historical *non-local* skill topology carry incremental information about the next invoked capability beyond (a) semantic retrieval and (b) finite-order transition history?

**H₀:** graph propagation over historical co-activation adds no predictive information beyond `embedding + Markov-k`.

This is a **procedural-structure predictiveness** study. It makes no claim about skill quality, utility, or policy improvement. Any wording implying value ("better skills", "improved outcomes") is out of scope for the report.

## 2. Data & node identity

- Source: all `execute_code` episodes in the event log, reconstructed as `context x → c₁ → c₂ → … → cₙ → outcome`.
- Nodes are **recurrence-audit clusters** (not registry entries). Each cluster carries its confidence tier `{low, medium, high}` from `recurrence-audit.py`. Cluster assignment is computed once, on the training window only, and frozen per cutoff.
- A *transition* is `(x, c₁..cₜ) → cₜ₊₁`. Episodes with < 2 clustered invocations are excluded and counted.

## 3. Temporal protocol (leakage discipline)

- Rolling cutoffs `T₁ < T₂ < T₃` chosen a priori at the 50 / 65 / 80 % episode quantiles by timestamp.
- Everything learned — clusters, edge weights, decay, Markov tables, embedding index contents, thresholds — from `< T`. Evaluation only on `≥ T`. Nothing is refit on the test side.
- Report each cutoff separately and pooled.

## 4. Models (fixed ladder, fixed hyperparameters — no search)

| # | Model | Locked parameters |
|---|-------|-------------------|
| M0 | Popularity (global frequency) | — |
| M1 | Embedding only (existing retriever, unmodified) | current config |
| M2 | Markov-1 | Laplace smoothing α = 1 |
| M3 | Markov-2, Markov-3 (backoff) | α = 1 |
| M4 | Embedding + Markov-k (k ∈ {1,2,3} chosen on the training window only) | reciprocal-rank fusion |
| M5 | **M4 + graph propagation** (embedding + Markov-k + graph) | seed = M1 top-5; propagation = personalized PageRank, depth ≤ 2, damping 0.85; **edge weight = decayed co-activation count (no success weighting)** |

Primary decay half-life: **30 d**. Half-lives `{∞, 7 d}` and success-filtered / success-weighted edges are **ablations only** (§6). No other values.

Combining rule for M4/M5: reciprocal-rank fusion. Fixed. Not tuned. Δtopology = M5 − M4 is therefore the marginal contribution of graph propagation *given* embedding and finite-order transition history — exactly the quantity H₀ concerns.

## 5. Endpoints

**Primary:** Recall@5 and MRR on the **embedding-failure slice** — transitions where the true `cₜ₊₁` is absent from M1's top-5. The slice is defined mechanically from M1 before any other model runs.

**Hypothesis test:** Δ = M5 − M4 on the primary endpoint, with 95 % bootstrap CI (1 000 resamples, resampling *episodes*, not transitions).

**Secondary:** the same metrics on the aggregate set; Δ vs M2/M3 alone.

**Stratification (mandatory second axis):** every metric reported by cluster-confidence tier.

```
                    low conf   medium   high
M4 embed+Markov       …          …       …
M5 embed+graph        …          …       …
Δ topology  [CI]      …          …       …
```

## 6. Pre-declared ablations (report all, tune none)

- edge construction: all trajectories (primary) vs successful-only vs success-weighted counts
- direct edges (depth 1) vs depth 2
- global topology vs context-conditioned (edges keyed on the effect class of `x`)
- decay half-life ∈ {30 d (primary), ∞, 7 d}

## 7. Power / stopping rule (computed *before* fitting)

Report: episode count, usable transitions, number of clusters and their sizes, failure-slice size per cutoff, per-tier counts.

**Minimums (locked):** ≥ 300 embedding-failure-slice transitions pooled across cutoffs, and ≥ 100 embedding-failure-slice transitions in the high-confidence tier. If either fails, the verdict is **UNDERPOWERED** plus an estimate of additional episodes needed. Do not proceed to §8. These thresholds are immutable once counts have been observed.

## 8. Verdict (one of three)

- **REJECT H₀:** CI of Δ excludes 0 on the primary endpoint at ≥ 2 of 3 cutoffs, and Δ does not shrink as cluster confidence rises. *Note: the test sets `≥T₁ ⊃ ≥T₂ ⊃ ≥T₃` are nested; the cutoff criterion is a **stability** criterion (the effect holds as the training window grows), not three independent tests. The pooled CI is the single hypothesis test.*
- **FAIL TO REJECT:** otherwise. Recommendation: use Markov transitions if M4 > M1 materially; drop the graph.
- **UNDERPOWERED:** §7 minimums not met.

Any other outcome pattern (e.g. Δ positive only in the low-confidence tier) is reported as FAIL TO REJECT with the anomaly flagged.

## 9. Prohibitions

No registry writes. No retriever changes. No graph service. No merge/split/decay/promotion logic. No new SKILL files. No hyperparameter search beyond §4/§6. No narrative summaries in place of numbers.

## 10. Deliverables

1. `topology-study-report.md`: §7 counts, §5 tables (per cutoff + pooled + per tier), §6 ablations, verdict.
2. `analysis/` — reproducible scripts + a manifest of frozen artifacts (cluster map, edge tables, cutoffs, seed).
3. A ≤ 10-line plain-language statement of what the verdict does and does not license.

*Recorded for later, outside this study:* Level-3 evidence definition ("no same-effect-class corrective invocation within N steps"); composite (live-reference, contract-validated) vs compiled (frozen, lineage + revalidation trigger) semantics.

---
**Changelog v1.0 → v1.1 (pre-data, per reviewer sign-off conditions):** (1) M5 redefined as M4 + graph so Δ isolates topology; (2) primary edge weight = decayed co-activation count, success weighting moved to ablations; (3) power minimums locked, "to confirm" removed; (4) nested-cutoff criterion labelled as stability, not independent replication. No other changes.
