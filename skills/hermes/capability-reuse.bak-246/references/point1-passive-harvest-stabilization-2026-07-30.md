# Capability-reuse point 1 — passive harvesting stabilization

Date: 2026-07-30
Coordinator: peer70 / Charon

## Scope

Stabilize point 1 from the Phase 0 next-step plan:

- peer70 is the canonical collector;
- every reachable Hermes peer has local `reuse-observer/events.jsonl` and fresh `reuse-aggregati/latest.json`;
- local analyzer runs every 15 minutes with explicit peer identity;
- peer70 collects peer summaries every 15 minutes;
- offline peers are recorded for later activation.

## Live peer health from peer70

At `Thu 30 Jul 2026 08:51:51 CEST`:

- peer70 `192.168.178.70`: HMP OK, node_id peer70
- peer84 `192.168.178.84`: HMP OK, node_id peer84
- peer106 `192.168.178.106`: HMP OK, node_id peer106
- peer138 `192.168.178.138`: HMP OK, node_id peer138
- trixie `192.168.178.136`: lightweight `/health` OK, not Hermes capability-reuse target
- peer105 `192.168.178.105`: timeout/offline
- peer128 `192.168.178.112`: timeout/offline

## Reusable procedure

1. From peer70, run live HMP health over the peer map and classify: reachable Hermes, lightweight/non-Hermes, offline.
2. On every reachable Hermes peer, ensure `batch-reuse-analyzer.py` exists under `~/.hermes/scripts/` and the capability-reuse skill/plugin tree is present.
3. Install analyzer cron with explicit identity; do not rely on hostname defaults:
   - `HMP_NODE_ID=<peer> python3 ~/.hermes/scripts/batch-reuse-analyzer.py --peer-id <peer>`
4. Run one shadow retrieval probe locally on each reachable Hermes peer to force a fresh `retrieval_event`.
5. Run the analyzer immediately and verify `~/.hermes/data/reuse-aggregati/latest.json` has the correct `peer_id`, fresh `generated_at`, and nonzero retrieval delta from the probe.
6. On peer70, run `capreuse-central-collector.py` to pull each peer's `latest.json` into `~/.hermes/data/reuse-aggregati/peers/<peer>.json` and write `fleet-latest.json`.
7. Add central collector cron on peer70 every 15 minutes.
8. Record offline peers as later activation work, not rollout blockers for the reachable set.

## Remediations discovered

- peer84 had `plugins.enabled: hmp,capability-reuse` as a scalar string; Hermes PluginManager treated both hmp and capability-reuse as not enabled. Rewriting it as a YAML list and adding `platforms.hmp.extra.node_id: peer84` restored `/hmp/health`.
- `batch-reuse-analyzer.py` had a bad fallback that defaulted unknown hosts to `peer106`. Harden it so explicit `--peer-id`/`HMP_NODE_ID` wins and hostname mapping is only a safe fallback.

## Cron pattern

Local analyzer cron:

```cron
*/15 * * * * HMP_NODE_ID=<peer> /usr/bin/python3 <home>/.hermes/scripts/batch-reuse-analyzer.py --peer-id <peer> ><home>/.hermes/logs/capreuse-analyzer.log 2>&1 # capreuse analyzer managed
```

peer70 central collector cron:

```cron
*/15 * * * * /usr/bin/python3 /home/fausto/.hermes/scripts/capreuse-central-collector.py >/home/fausto/.hermes/logs/capreuse-central-collector.log 2>&1 # capreuse central collector managed
```

## Verification observed

Injected one point-1 shadow retrieval probe on each reachable Hermes peer and ran analyzer:

- peer70: retrieval_event_id `6a4cf37ac748440c`, latest generated `2026-07-30T06:51:26Z`, retrieval_total 1
- peer84: retrieval_event_id `99cfdc427bd6434f`, latest generated `2026-07-30T06:51:27Z`, retrieval_total 1
- peer106: retrieval_event_id `5050aa9921e94eaa`, latest generated `2026-07-30T06:51:30Z`, retrieval_total 1
- peer138: retrieval_event_id `4bddc74894834b4e`, latest generated `2026-07-30T06:51:41Z`, retrieval_total 1

peer70 central collector output:

- file: `/home/fausto/.hermes/data/reuse-aggregati/fleet-latest.json`
- generated_at: `2026-07-30T06:52:13Z`
- ok_count: 4
- fail_count: 0

## Known non-blocking anomaly

Fresh probe deltas showed `read_only_mutating_candidates_seen_together`. In passive shadow this means semantic candidates span effect classes and is useful evidence for later threshold/effect-class hardening. It is not a point-1 collection blocker.

## Offline follow-up

Bring these back into the set later:

- peer105: timeout / no route during this run
- peer128: timeout / no route during this run

When reachable: install v2.4.1, add analyzer cron with explicit `--peer-id`, run one shadow retrieval probe, run analyzer, then rerun central collector.
