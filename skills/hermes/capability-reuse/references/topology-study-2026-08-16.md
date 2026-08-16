# Topology Study v1.1 — Execution Record (2026-08-16)

Frozen prereg `topology-study-prereg-v1.1.md` executed read-only on peer70.
Verdict: **UNDERPOWERED** (stopped at §7; §§4–8 not run, per prereg).

## Prerequisite blocker (durable — do not rediscover)

**`recurrence-audit.py` v1.2 does NOT emit confidence tiers `{low, medium, high}`.**
The prereg §2 assumes clusters carry tiers "from recurrence-audit.py" — the
script only emits OPERATION_PATTERNS classes (8 patterns + `unknown/other`)
and a binary "high-value (>=3)" flag. Consequences:
- §5 tier stratification and the §7 high-conf minimum (≥100) are
  structurally unreachable until the script emits tiers.
- Fixing tier emission is a **prerequisite**, not an experiment redesign
  (prereg §9 prohibits redesign; the gap must be recorded, not patched
  silently).

## Event-log source map (execute_code history)

All read-only; dedup by `event_id` (fallback `data.event_id`, else synthetic):

| Source | Path | Events | Notes |
|---|---|---|---|
| Pre-2.4.16 log | `~/.hermes/data/reuse-observer/events.jsonl.bak-pre2416` | 2801 | main historical log, 1–14 Aug |
| Current live | `~/.hermes/data/reuse-observer/events.jsonl` | 91 | v2.5.0 |
| Collector raw peer70 | `capreuse-central/raw/peer70/events.jsonl` (in `~/.hermes/data/capreuse-backup-20260813-1735/capreuse-data.tar.gz`) | 102 | 29–30 Jul |
| Collector raw peer106 | same tar → `capreuse-central/raw/peer106/events.jsonl` | 35 | |
| peer138 export | `~/.hermes/data/capreuse-backup-20260813-1735/peer138/events.jsonl` | 317 | **no `event_type` field** → excluded from started/completed counts |

Event kinds of interest: `execute_code_started_event`, `execute_code_completed_event`,
`retrieval_event`, `observation_event`, `alternate_execution_event`. Timestamps live
in `timestamp` (top-level) or `data.timestamp`.

## §7 inventory (frozen counts)

- 3352 events dedup; 79 started / 78 completed
- **16 episodes** (sessions with ≥1 execute_code); 8 excluded (<2 invocations); 8 usable
- **63 usable transitions**; **4 clusters** (unknown/other 71, hmp_healthcheck 6,
  json_parse 1, cron_management 1)
- Cutoffs (episode min-ts quantiles): T1 50% = 2026-08-13T16:15:25Z, T2 65% = 16:28:27Z,
  T3 80% = 19:21:45Z; transitions per cutoff: 25 / 26 / 63
- Locked minimums: ≥300 failure-slice pooled (fail: ≤63) and ≥100 high-conf tier
  (fail: 0). Both unmet → UNDERPOWERED per §7.

## Estimated data needed

~63 transitions over ~13 days ≈ 4.8/week → ≥600–1200 total transitions for the
failure-slice minimum = **2.5–5 years of natural passive harvest**. Acceleration
paths (operator decision, outside study): `calibration_probe` traffic (already in
event vocabulary), multi-peer aggregation (141/138/58 publish manifests; current
log is peer70-dominated), plus the tier prerequisite fix.

## Artifacts

`analysis/` under the capability-reuse skill dir: `inventory.py` (reproducible
read-only inventory), `topology-study-report.md`, `manifest.json` (frozen counts,
cutoffs, sources). No registry writes, no retriever changes, no skill creation,
no graph infra — all §9 prohibitions respected.
