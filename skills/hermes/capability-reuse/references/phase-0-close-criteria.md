# Phase 0 Close Criteria — Empirical Validation Checklist

*From Fausto's review: distinguish "Phase 0 tooling complete" from "Phase 0 gates met"*

## 1. Recurrence Corpus

- [ ] Total episodes analyzed (N)
- [ ] Occurrences per cluster (≥3 clusters with ≥5 each)
- [ ] Separation by session/day
- [ ] % of corpus covered by top-10 clusters
- [ ] Debug/retry loops excluded from count
- [ ] Estimated avoidable: code volume, latency, failures, review cost

## 2. Post-execution Benchmark (Dataset B)

- [ ] ≥100 episode pairs labeled
- [ ] Class distribution reported (same operation / related / unrelated / uncertain / incompatible)
- [ ] Precision and recall for clustering / fingerprint
- [ ] Confusion matrix
- [ ] Principal false positives and false negatives documented

## 3. Pre-execution Retrieval Benchmark (Dataset C)

- [ ] Request/context → capability pairs labeled
- [ ] Hard negatives included
- [ ] Tuning/holdout split documented
- [ ] Top-1 precision on holdout
- [ ] Intervention threshold and margin chosen
- [ ] False matches between incompatible effect classes checked

## 4. Predeclared Gates

- [ ] Minimum recurring-value threshold defined
- [ ] Minimum holdout precision (or lower confidence bound)
- [ ] Prohibited false-match classes defined (especially read-only vs mutating)
- [ ] Maximum acceptable pre-flight latency
- [ ] Human review budget defined
- [ ] Pass/fail per gate

## 5. Hook Conformance

- [ ] Hermes version/commit pinned
- [ ] Plugin source/path/version/hash verified
- [ ] 15 tests detailed results
- [ ] Integration mode determined (pre_generation / tool_boundary / unsupported)
- [ ] Inventory of alternate execution surfaces
- [ ] Hook latency p50/p95/p99

## 6. Registry Evidence

- [ ] read_only classification justified for each capability
- [ ] Trust basis documented for each capability version
- [ ] Contract hash, owner, and review date recorded
- [ ] Equivalence policy defined where applicable

## Official State Transitions

```
Phase 0 tooling complete              → 7/7 steps implemented
Phase 0 empirical validation pending  → evidence not yet meeting gates
Live-shadow data acquisition          → authorized, no behavioral change
Phase 1B canary                       → NOT authorized until all gates pass
```

## Burn-in Exit Criteria (C1-C10)

| # | Criterion | Threshold | Measurement |
|:-:|-----------|-----------|-------------|
| C1 | Episodes collected | ≥200 execute_code across all peers | `recurrence-audit.py` |
| C2 | Recurring clusters | ≥3 clusters with ≥5 occurrences each | `code-fingerprint.py` |
| C3 | Top-10 coverage | ≥40% of episodes | Report metric |
| C4 | Pre-exec labels | ≥100 pairs (tuning+holdout+hard negatives) | Manual labeling |
| C5 | Post-exec labels | ≥100 pairs for fingerprint validation | Manual labeling |
| C6 | Min precision | Top-1 ≥70% on holdout | Benchmark |
| C7 | Effect false matches | Zero read-only↔mutating false positives | Benchmark |
| C8 | Hook conformance | 15/15 tests passed | `conformance-suite.py` |
| C9 | Hook latency | p50 <10ms, p95 <50ms, p99 <200ms | Telemetry |
| C10 | Thresholds calibrated | intervention_threshold + margin on tuning set | Benchmark |
