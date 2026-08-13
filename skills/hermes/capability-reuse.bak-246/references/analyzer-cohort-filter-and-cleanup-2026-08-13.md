# Analyzer cohort filter fix + legacy cleanup — 2026-08-13

Fausto asked to delete "legacy events and peer138 events" from the
capability-reuse corpus. Investigation showed most of what looked legacy was
an analyzer labeling artifact; the actual cleanup was smaller and precise.
Same-day context: peer141 (Stella) was onboarded replacing peer105 (see
hermes-hmp `references/onboard-full-peer.md`).

## Lesson 1 — Verify before deleting (don't trust the label)

- `latest.json` cohort section said: `legacy_or_pre_events: 1629`, clean: 0.
- Direct event check: ALL events had current deployment_id
  (`dep-v245-review-6a6d9330`), cohort_label `v2.4.5_review_queue`,
  plugin_version `2.4.6`, peer_id `peer70` → NOT legacy. The analyzer's
  hardcoded `v2.4.4_clean_live`/`2.4.4` filter was the artifact.
- Real legacy lived elsewhere:
  - `capreuse-central/raw|aggregates|reports/` — July copies (peer70/106/128/84)
  - `reuse-aggregati/runs/*202607*` — 319 July run files
  - peer138's REMOTE `events.jsonl` (317 lines) — on the peer itself
    (`/root/.hermes/data/reuse-observer/events.jsonl`), NOT in central.

## Lesson 2 — Backup before deleting

```bash
cd ~/.hermes/data && BK=capreuse-backup-<date> && mkdir -p $BK
tar -czf $BK/capreuse-data.tar.gz reuse-observer/events.jsonl capreuse-central/ reuse-aggregati/runs/
scp -q root@<peer>:/root/.hermes/data/reuse-observer/events.jsonl $BK/peer<X>/
```

Deletion is otherwise irreversible. Backup = revertibile (Fausto's soft-mode rule).

## What was deleted

peer70:
- `capreuse-central/raw/{peer70,peer106,peer128,peer84}`, `aggregates/*`, `reports/*`
- `reuse-aggregati/runs/*202607*` (all 319 July runs)

peer138 remote (`root@192.168.178.138`):
- `events.jsonl` + `cursor.json` + `latest.json`
- `reuse-aggregati/review/queue-latest.*` and `rollups/*` (derived from its events)

## Analyzer fix

Filter now reads cohort.json dynamically (deployment_id + cohort_label +
plugin_version); cohort.json plugin_version corrected 2.4.5 → 2.4.6 (stale
manifest). Result: 1659 total, 1659 clean, 0 legacy, 98 retrievals
(61 independent). Patch applied to BOTH copies (runtime + skill) — they had
drifted (skill copy was v2.4.6 with extra API, runtime was v2.4.4), but both
carried the same hardcoded filter line.

## Chain-error interpretation (shadow mode)

306 errors / 98 retrievals:
- 98 retrievals × 3 error types (identifier_mismatch, start_count=0,
  completion_count=0) = 294 — shadow retrievals never start execute_code
- 12 `execute_code_started` without retrieval = 12 — direct raw execute_code

Expected in shadow mode; chain check is designed for ACTIVE mode only.

## Reversibility

Full restore possible from `~/.hermes/data/capreuse-backup-20260813-1735/`
(events.jsonl 172KB tar + peer138 events.jsonl 396KB).
