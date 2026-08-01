# Capability-reuse provenance, rollups, and review export — 2026-07-30

Implemented next build step for faster meaningful data gathering without contaminating formal evidence.

## What changed

1. Retrieval provenance at event source
   - Runtime/source plugin `event_store.emit_retrieval()` now writes `data.provenance`.
   - Default stream: `organic_live`.
   - Override stream with `CAPABILITY_REUSE_PROVENANCE=operator_seeded|calibration_probe|organic_live`.
   - Optional detail: `CAPABILITY_REUSE_PROVENANCE_DETAIL`.
   - Invalid streams fall back to `organic_live`.

2. Analyzer provenance classification
   - `batch-reuse-analyzer.py` recognizes explicit `data.provenance`, `source`, `source_stream`, and marker text.
   - Supported buckets:
     - `organic_live`
     - `operator_seeded`
     - `calibration_probe`
     - `legacy_unclassified` in rollups for old run files without provenance.

3. 24h / 7d rollups
   - Built from `~/.hermes/data/reuse-aggregati/runs/*.json`.
   - Output:
     - `~/.hermes/data/reuse-aggregati/rollups/24h.json`
     - `~/.hermes/data/reuse-aggregati/rollups/7d.json`
     - `~/.hermes/data/reuse-aggregati/rollups/latest.json`
   - Includes totals, peers, event-type counts, candidate counts, recurring candidates, provenance buckets, top-score buckets, anomalies, and review candidates.

4. Human review queue export
   - Generated from the full raw local event log, not only the latest delta.
   - Output:
     - `~/.hermes/data/reuse-aggregati/review/queue-latest.jsonl`
     - `~/.hermes/data/reuse-aggregati/review/queue-latest.csv`
   - CSV columns include timestamp, peer, provenance, capability, score, score bucket, effect class, candidate count, shadow/intervened flags, blank label/notes fields, event/session IDs, and redacted user-message preview.

## Verification on peer106/root profile

Commands run:

```bash
python3 /root/.hermes/skills/hermes/capability-reuse/tests/test_batch_reuse_analyzer.py
cd /root/.hermes/skills/hermes/capability-reuse && python3 -m unittest discover -s tests -p 'test_*.py'
cd /root/.hermes/skills/hermes/capability-reuse && python3 scripts/conformance-suite.py --profile local-controller --output /tmp/capreuse-conformance-after-provenance-rollups.json
python3 /root/.hermes/scripts/batch-reuse-analyzer.py --peer-id peer106 --print-summary
```

Observed results:

- batch analyzer focused tests: 7/7 OK.
- full source test discovery: 52/52 OK.
- local-controller conformance: 15/15 OK.
- analyzer generated latest stats, rollups, JSONL review queue, and CSV review queue.
- generated CSV contained 30 rows at verification time.
- generated 24h rollup showed 87 retrieval events, with provenance split `legacy_unclassified=86`, `organic_live=1` at verification time.

## Operational note

For formal evidence, treat `legacy_unclassified` as unusable for provenance-sensitive holdout claims. It can still be used for dashboard/review triage. Only new retrieval events emitted after this patch carry explicit provenance by default.
