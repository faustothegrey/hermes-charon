# Phase 0 Empirical Closure Report — capability-reuse v2.1.0

Generated: 2026-07-27T14:35:06.974516Z

Status: PHASE_0_EMPIRICAL_CLOSURE_PASS

Qualification: Dataset C includes historical requests, burn-in hook-visible prompts, and synthetic registry-calibration prompts; reviewer may still require independent human labeling before formal active Phase 1B authorization.

## C1-C10 gates

| Gate | Result | Evidence |
|------|:------:|----------|
| C1 Episodes collected ≥200 | PASS | 301 execute_code tool calls across 23 sessions |
| C2 ≥3 recurring clusters ≥5 | PASS | 5 clusters: json_aggregation=157, file_patch=59, hmp_healthcheck=24, hmp_send=6, test_validation=6 |
| C3 Top-10 coverage ≥40% | PASS | 100.0% |
| C4 Pre-exec labels ≥100 | PASS | 120 pairs; 48 historical/burn-in, remainder synthetic calibration |
| C5 Post-exec labels ≥100 | PASS | 150 deterministic post-exec pairs |
| C6 Top-1 precision ≥70% | PASS | holdout precision 100.0%, recall 100.0% |
| C7 read-only↔mutating false matches = 0 | PASS | 0 |
| C8 Hook conformance 15/15 | PASS | peer70, peer128, peer138 all 15/15 |
| C9 Hook latency p50<10ms p95<50ms p99<200ms | PASS | max p50 6.05ms, p95 6.89ms, p99 7.59ms |
| C10 Thresholds calibrated | PASS | active threshold 0.65, hard effect false-match gate, allowlist hmp-healthcheck only |

## Fresh v2.1.0 burn-in

- peer128 batch-10: positives 50/50, negatives false-positive 0/50, correlation errors 0, events 580.
- peer138 batch-10: positives 50/50, negatives false-positive 0/50, correlation errors 0, events 580.

## Evidence files

See this directory for raw JSON/JSONL artifacts and SHA256SUMS.
