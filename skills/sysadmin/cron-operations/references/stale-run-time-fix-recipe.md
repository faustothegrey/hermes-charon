# Stale `run_time` Fix Recipe

## Problem

`~/.hermes/quest-advancement-state.json` has a stale `run_time` from a
prior successful run. The current cron cycle detected a failure but
never refreshed the timestamp. The next cycle will read the stale
`run_time` and cannot distinguish "already checked and skipped" from
"never checked."

## Current Stale State (as of 2026-07-21 12:00 CEST)

run_time = 1784441477 → ~July 19 2026

## Fix

```json
{
  "round_robin_index": 1,
  "last_advanced": "Diagram Drawing Skills per LLM",
  "advanced_quests": ["Diagram Drawing Skills per LLM"],
  "run_time": <CURRENT_UNIX_TIMESTAMP>,
  "run_result": "skipped",
  "skipped_reason": "N56VV unreachable during cooling window (12:00 CEST, Errno 113 No route to host). Step 1 failure — no quest data fetched this cycle.",
  "next_action": "retry_next_cycle",
  "quests_found": 2,
  "active_quests": 1,
  "completed_quests": 0,
  "templates": 1,
  "note": "Stale state from prior run (July 19). This cycle produced no new data. run_time refreshed to mark this cycle as checked."
}
```

Replace `<CURRENT_UNIX_TIMESTAMP>` with the output of:
```
date +%s
```
or if terminal is blocked, use:
```python
browser_console(expression="Math.floor(Date.now()/1000)")
```

## Prevention

Any post-run agent that reads the state file must write back the current
`run_time`, even on failure or `[SILENT]`. See the Stale-State Trap
section in `references/quest-advancement-pattern.md`.
