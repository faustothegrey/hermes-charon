# Capability-reuse: human inspection dashboard + accelerated meaningful data plan

Date: 2026-07-30

## A. Visual inspection path

Implemented on peer70:

- Generator: `/home/fausto/.hermes/scripts/capreuse-dashboard.py`
- Dashboard: `/home/fausto/.hermes/data/reuse-aggregati/dashboard.html`
- Refresh cron:

```cron
*/15 * * * * /usr/bin/python3 /home/fausto/.hermes/scripts/capreuse-dashboard.py >/home/fausto/.hermes/logs/capreuse-dashboard.log 2>&1 # capreuse dashboard managed
```

The dashboard is a static, dependency-free HTML file. It reads:

- `/home/fausto/.hermes/data/reuse-aggregati/fleet-latest.json`
- `/home/fausto/.hermes/data/reuse-aggregati/peers/*.json`

Current panels:

1. Fleet summary: OK/fail peer counts, peer snapshots, retrieval deltas.
2. Peer freshness and volume: generated_at, event deltas, retrieval deltas, anomalies.
3. Candidate counts: aggregate candidate frequency by capability version.
4. Top score buckets: quick view of retriever confidence distribution.
5. Anomalies: e.g. mixed read-only/mutating candidate sets.
6. Human review queue: peer/candidate/count rows for labeling prioritization.
7. Inspection checklist: reminders to separate organic data from probes/calibration.

Verification result:

- dashboard generated successfully;
- file size 6183 bytes;
- expected text and peers present: peer70, peer84, peer106, peer138;
- dashboard cron present.

## B. Plan to speed up gathering of meaningful data

Goal: increase useful labeled/request-candidate examples without contaminating the formal organic holdout.

### Principle: three separate streams

Do not collapse all observations into one bucket. Keep provenance explicit:

1. `organic_live`
   - Real user/operator requests.
   - Highest value for formal holdout.
   - Slowest source.

2. `operator_seeded`
   - Realistic tasks intentionally issued by Fausto or peer70, but still semantically useful operational traffic.
   - Good for discovering recurring candidates quickly.
   - Usable for tuning only if marked as seeded.

3. `calibration_probe`
   - Controlled prompt packs: positives, hard negatives, mutating composites, informational requests, code/docs-generation requests.
   - Best for threshold/margin sweep and safety tests.
   - Must not be claimed as organic precision evidence.

### Week-1 acceleration loop

Run this daily for 3-7 days:

1. Organic collection continues passively
   - Current 15-minute local analyzer and central collector are enough.
   - Do not change active scope.

2. Add small operator-seeded sessions
   - 5-10 short real operational prompts per day across reachable peers.
   - Examples:
     - check HMP health for peer70/peer84/peer106/peer138;
     - inspect collector freshness;
     - explain latest anomaly;
     - compare latest candidate counts;
     - ask for safe next step on a peer issue.
   - Keep them as actual agent conversations, not raw JSON injection.
   - Mark source as `operator_seeded` if/when event schema supports source tags.

3. Run a controlled calibration pack separately
   - 40-80 prompts/day per reachable Hermes peer is enough at this scale.
   - Split:
     - 30% clear positives for hmp-healthcheck / peer-heartbeat;
     - 30% hard negatives: “do not check”, “what is HMP healthcheck”, docs/code generation;
     - 25% mutating composites: “check health and restart if unhealthy”, “ping then send message”;
     - 15% ambiguous/edge prompts.
   - Store results under a separate path, e.g. `/home/fausto/.hermes/data/reuse-calibration/`, not mixed with organic dashboard by default.

4. Human label only the review budget
   - Use dashboard candidate queue first.
   - Label max 15 candidate sets/week, as Gate 4 says.
   - For each row record:
     - prompt/source;
     - expected capability or NONE;
     - effect class expected;
     - whether candidate set contains dangerous cross-effect confusion;
     - whether it is admissible for holdout.

5. Weekly threshold sweep
   - Use calibration + labeled seeded data for threshold/margin tuning.
   - Reserve organic labeled rows as holdout.
   - Required before closure: ≥85% precision on holdout and zero read_only↔mutating false matches.

### Concrete implementation backlog

1. Add provenance/source field to retrieval_event
   - Values: `organic_live`, `operator_seeded`, `calibration_probe`, `engineering_probe`.
   - Backward compatible default: `organic_live` unless env var or hook_context says otherwise.

2. Add central long-window rollup
   - Current latest.json is delta-based.
   - Add peer70 weekly rollup from `runs/*.json` so the dashboard can show 24h/7d trendlines.

3. Add label queue file
   - `/home/fausto/.hermes/data/reuse-labeling/queue.jsonl`
   - Dashboard links or table rows should map candidate sets to review IDs.

4. Add calibration runner
   - Stdlib script that calls production retriever in `shadow_mode=True` against a prompt pack.
   - Writes separate calibration events/results, not formal organic events.

5. Add CSV export for human review
   - `/home/fausto/.hermes/data/reuse-labeling/review-queue.csv`
   - Columns: review_id, source, peer, prompt_preview, top_candidate, top_score, candidate_set, expected_label, human_decision, notes.

### Expected speedup

- Organic-only: probably days/weeks before enough useful edge cases.
- With operator-seeded traffic: useful recurring-candidate signal within 1-2 days.
- With calibration probes: threshold/safety curves within hours, but not sufficient alone for formal closure.

Recommended next implementation: add source/provenance field + 24h/7d rollup + review CSV export. That gives Fausto a safe human-labeling workflow before we generate more data.
