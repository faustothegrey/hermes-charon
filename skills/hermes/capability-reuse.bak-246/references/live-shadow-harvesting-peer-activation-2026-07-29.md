# Live-shadow harvesting peer activation — 2026-07-29

## Trigger

Use this when Fausto asks to ensure capability-reuse data harvesting/live-shadow collection is active across the HMP mesh.

## Operational sequence

1. Ask peer70 for the current active peer set first. Do not rely only on the static peer map; peer70 has the current online/offline/cooling view.
2. Contact every active peer returned by peer70. For each peer, ask for a local check of:
   - capability-reuse plugin enabled/loaded while preserving `hmp`
   - `~/.hermes/data/reuse-observer/events.jsonl` exists
   - latest `retrieval_event` timestamp/count is fresh
   - `~/.hermes/data/reuse-aggregati/latest.json` exists and has `generated_at` / `events_processed`
3. Have a brief HMP conversation with every active peer before the final check. A one-sentence prompt is enough; the point is to generate a real turn that should cause a fresh `retrieval_event` if hooks are active.
4. Recheck after the conversation. Treat stale retrieval timestamps as not working even if files exist.
5. If a peer is missing analyzer output but has fresh events, ask it to run/schedule `batch-reuse-analyzer.py` and verify `latest.json`.
6. If a peer has plugin files on disk but no fresh retrieval events, ask it to add `capability-reuse` to `plugins.enabled` while preserving `hmp`, reload/restart the gateway if needed, then produce a fresh probe and rerun the checks.
7. Report per peer as `OK`, `PARTIAL`, or `FAIL`; include exact timestamps/paths/counts. Do not collapse partials into OK.

## Status meanings

- `OK`: plugin enabled, fresh retrieval event observed after the brief conversation/remediation, and `reuse-aggregati/latest.json` exists.
- `PARTIAL`: one of the components works but another is missing/stale, e.g. fresh `events.jsonl` but no analyzer output, or integrated dual-plane harvesting but plugin not installed in `~/.hermes/plugins/`.
- `FAIL`: plugin not enabled, no events, or events are stale after a fresh HMP turn.
- `UNRESOLVED`: peer accepted work but remains `working`/`delivering` beyond the timeout; do not infer success.

## Session observations worth reusing

- peer58 initially had plugin files and stale events, but after explicit activation/remediation it reported `plugins.enabled=[hmp, capability-reuse]`, fresh `retrieval_event`, `latest.json`, and a cron for analyzer. Lesson: enabled status plus a fresh probe is stronger evidence than historical file presence.
- peer138 already harvested events but lacked `latest.json`; asking it to run/schedule the analyzer resolved the gap.
- peer70 may report harvesting via an integrated dual-plane path even if the plugin is not copied into `~/.hermes/plugins/`; record that as `PARTIAL` unless the requested standard explicitly accepts integrated harvesting as sufficient.
- peer84 can remain in `working` for a long time during remediation. Keep polling, but if it exceeds the task timeout, report `UNRESOLVED` rather than guessing.
