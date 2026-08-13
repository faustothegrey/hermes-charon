# External review verdict — 2026-07-27

## Accepted official status

```text
Phase 0 tooling:                  complete
Phase 0 corpus acquisition:       sufficient volume collected
Phase 0 implementation tests:     pass
Phase 0 empirical validation:     incomplete
Formal Phase 0 closure:           not yet
Passive live shadow:              authorized
Formal Phase 1B authorization:    not authorized
```

## Summary

The reviewer accepted that v2.1.0 is a meaningful implementation/tooling release and that the archive is well formed:

- packaged SHA-256 checks pass;
- no unsafe ZIP paths;
- installs in isolated Hermes home;
- 37 regression tests pass;
- local conformance harness reports 15/15;
- 301 `execute_code` calls across 23 sessions are packaged;
- event-chain and peer burn-in reports are included;
- six previous implementation blockers appear fixed.

However, the reviewer rejected the claim `PHASE_0_EMPIRICAL_CLOSURE_PASS` because the empirical methodology is not independent enough.

## Gate assessment from reviewer

| Gate | Assessment |
|------|------------|
| C1 ≥200 calls | Pass with qualification |
| C2 ≥3 recurring clusters | Provisional pass; needs manual cluster validation |
| C3 ≥40% coverage | Likely pass; reported 100% calculation is wrong |
| C4 ≥100 pre-exec labels | Fail — labels not manual/independent |
| C5 ≥100 post-exec labels | Fail — deterministic/circular labels |
| C6 precision ≥70% | Invalid measurement — evaluates keyword classifier, not true retriever |
| C7 zero effect mismatches | Not independently demonstrated |
| C8 15/15 conformance | Local harness pass; pinned runtime dispatcher conformance unproven |
| C9 latency budget | Provisional pass for local benchmark |
| C10 calibrated thresholds | Fail — threshold selected, not calibrated |

## Methodology fixes required

1. Human-label Dataset B: 100–150 post-execution pairs, blind to regex buckets, covering same reusable operation, related-but-different, unrelated, incompatible, and uncertain.
2. Human-label Dataset C: at least 100 real or independently authored hook-visible requests. Synthetic data may be used for development but not as full holdout.
3. Freeze a real holdout: no template overlap, variant suffixes, or repeated base prompts across tuning/holdout.
4. Evaluate the actual retriever: candidate scores, hard filters, margin, eligibility, contracts — not a second keyword classifier.
5. Run threshold sweep: precision, recall, false effect matches, intervention count by threshold and margin.
6. Perform genuine runtime conformance: raw evidence from pinned CLI and gateway dispatcher. Delegation may remain unsupported/unknown, but must not be simulated as passed.
7. Manually validate recurrence clusters: exclude debugging/retry loops and show recurrence across sessions or days.

## Consequence

Official status must be downgraded to:

```text
PHASE_0_TOOLING_AND_CORPUS_COLLECTION_COMPLETE
EMPIRICAL_LABELING_AND_INDEPENDENT_VALIDATION_PENDING
```

Do not claim formal Phase 0 closure until the above evaluation evidence exists and is reviewed.
