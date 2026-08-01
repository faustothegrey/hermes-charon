# Phase 0 closure playbook for capability-reuse

Use this when Fausto asks to close Phase 0 or prepare formal review evidence for capability-reuse.

## Order of operations

1. Reconfirm scope before running evidence:
   - Passive live-shadow may be GO.
   - Formal active Phase 1B is not automatically authorized by a closure run.
   - Active allowlist should remain narrow (`hmp-healthcheck@1.0.0`) until reviewer acceptance.
   - Mutating capabilities such as `hmp-send` stay unsafe/not active.

2. Build the empirical evidence bundle under `evidence/phase0/`:
   - `phase0-empirical-summary.json`
   - `dataset-b-post-exec-pairs.jsonl`
   - `dataset-c-pre-exec-pairs.jsonl`
   - peer conformance reports
   - peer burn-in aggregates
   - selected redacted event chains
   - deployment manifests
   - `SHA256SUMS`

3. Phase 0 gates to report explicitly:
   - C1: at least 200 collected episodes/tool-call samples.
   - C2: at least 3 recurring clusters with at least 5 occurrences each.
   - C3: declared top-N coverage threshold.
   - C4: at least 100 pre-exec request/capability labels.
   - C5: at least 100 post-exec/effect labels.
   - C6: holdout precision above the predeclared threshold.
   - C7: zero read-only <-> mutating false matches.
   - C8: pinned-runtime conformance reports from peer70, peer128, and peer138.
   - C9: hook latency p50/p95/p99 below budget.
   - C10: thresholds and effect gates documented.

4. Run fresh validation before claiming closure:
   - `python3 -m compileall -q plugin tests scripts ~/.hermes/plugins/capability-reuse`
   - `python3 -m unittest discover -s tests -q`
   - `python3 scripts/conformance-suite.py`
   - peer-scoped active burn-ins using `scripts/active-canary-burnin.py peer128` and `peer138`, aggregated over 10 runs when possible.

5. Pinned-runtime gotcha:
   - On peer138, use the Hermes venv Python for conformance when system Python lacks runtime deps such as `yaml`: `/usr/local/lib/hermes-agent/venv/bin/python`.
   - Capture this as the interpreter used in the evidence; do not generalize it as a permanent tool failure.

6. Evidence qualification:
   - If Dataset C includes synthetic registry-calibration prompts, mark Phase 0 empirical closure as PASS WITH QUALIFICATION.
   - State clearly that an external reviewer may still require independently human-labeled Dataset C before formal active Phase 1B authorization.

7. Sync and registry:
   - Sync the updated skill/evidence to peer70 first.
   - Publish peer70 registry so it reports capability-reuse v2.1.0.
   - Distribute the updated skill/evidence to peer128 and peer138.
   - Verify `SHA256SUMS` on each peer.

## Reporting style

For Fausto, answer operationally and tersely: PASS/NO-GO status first, then the key metrics and evidence paths. Do not blur evidence PASS into formal active authorization.