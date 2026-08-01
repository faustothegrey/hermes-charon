# Backup Monitor — Pre-Run Already Persisted, Repeat Detection, Silent Pattern

## Scenario

A cron job with `"script": "backup_monitor.py"` in jobs.json runs the
script as a pre-run subprocess before the agent session starts. The
script succeeds, writes `~/.hermes/backup_status.json`, and prints:

```
[OK] Status persisted to /home/fausto/.hermes/backup_status.json
      Peers: 4 total, 0 ok, 4 error/unreachable
```

## Decision Tree

```
## Script Output exists with backup_monitor.py completion message
           │
           ▼
    Status file on disk?       NO      Compose manually from
    (read_file)               ───────→ ## Script Output's pre-run
                                     JSON (unlikely — script already
                                     reports "persisted")
           │ YES
           ▼
    Timestamp in status       NO      Pre-run script may have failed
    matches ## Script                 after stdout. Use fallback
    Output's epoch?                   data sources or browser.
           │ YES
           ▼
    DATA IS FRESH. Skip all re-running and re-writing.
           │
           ▼
    Are peer states                    YES → [SILENT]
    identical to previous run?
           │
           NO
           ▼
    REPORT delta (error type change,
    new offline peer, recovery, etc.)
```

## The Pre-Run Confirmation Signal

When `## Script Output` contains the exact format:

```
[OK] Status persisted to /home/fausto/.hermes/backup_status.json
      Peers: N total, X ok, Y error/unreachable
```

This is backup_monitor.py's standard completion message (lines 57-58).
It confirms the script:
1. Ran to completion (not timed out)
2. Successfully parsed input data
3. Wrote `backup_status.json` to disk

**Do NOT re-run the script. Do NOT manually re-compose the status
file.** Both are redundant — the pre-run script already produced the
canonical output.

## Traceability: `[OK] Status persisted` Doesn't Mean "Fresh Data"

A subtle but critical nuance discovered in this session:

The pre-run `backup_monitor.py` script reads from `~/_cron_backup_data.json`
and writes the processed summary to `~/.hermes/backup_status.json`. If
`_cron_backup_data.json` itself is stale (e.g., last updated 4 days ago
from a failed collection run), the pre-run script will:

1. ✅ Read the stale JSON successfully
2. ✅ Count peers and classify esito correctly
3. ✅ Write `backup_status.json` with TODAY'S `timestamp`
4. ✅ Print `[OK] Status persisted to ...`
5. ❌ Contain `updated_at` and `updated_at_str` from 4 days ago

**The tell:** `timestamp` (file write time) and `updated_at` (data collection
time) are DIFFERENT values. A delta >1 hour between them means the pre-run
processed stale input — it didn't re-query the peers.

**How to detect:**

```python
read_file("~/.hermes/backup_status.json")
# Compare:
#   "timestamp"       → when this file was written (always recent)
#   "updated_at"      → when the data was actually collected (may be old)
#   "updated_at_str"  → human-readable version of updated_at
```

| `timestamp - updated_at` | Meaning | Action |
|---|---|---|
| < 5 minutes | Data is fresh | Proceed normally |
| 1-60 minutes | Slightly stale — acceptable for low-frequency monitoring | Note in report |
| > 1 hour | Data is stale — pre-run processed cached input | Report with staleness warning |
| > 24 hours | Critically stale — no recent collection succeeded | Flag for human attention |

**Real-world example (2026-07-28):** The pre-run reported `[OK] Status
persisted` with `timestamp: "2026-07-28T11:00:00"` (fresh) but
`updated_at: 1784912485.7078257 ("2026-07-24 19:01:25")` — **4 days
stale**. The `_cron_backup_data.json` contained the same 4-day-old
data. All 4 peers were in the same error state as July 24, so the
stale data still represented the current situation — but the agent
should have noted the staleness in its decision rather than silently
accepting `[OK] Status persisted` as meaning "fresh data."

**Takeaway:** Always check `updated_at` vs. `timestamp` in the status
file, not just the presence of the `[OK]` completion message. A pre-run
script that processes cached input is not the same as a script that
successfully queried the network.

Even if the agent wanted to re-run backup_monitor.py, the following all
fail in cron mode:

| Attempt | Result | Reason |
|---------|--------|--------|
| `terminal("python3 backup_monitor.py < data.json")` | `tirith:unknown` | Shell redirect triggers Tirith |
| `terminal("python3 _cron_bm_inline.py")` | `tirith:unknown` | All `terminal()` blocked in cron |
| `execute_code(...)` | `BLOCKED` | Independent cron guard for execute_code |
| `write_file("~/new_runner.py")` + `terminal(...)` | Both blocked | Writing a new runner script is itself pointless — the `terminal()` call that runs it is blocked |
| `subprocess.run([...])` inside execute_code | BLOCKED | execute_code is blocked independently |

**The only non-blocked paths:** `write_file` (to persist manually if the
pre-run script hadn't written), `read_file` (to verify), `browser_navigate`
(as a fallback data source).

## Confirming the Status File is Already Correct

Since the pre-run script already wrote the canonical file, read and
compare:

```python
read_file("~/.hermes/backup_status.json")
```

The status file contains `updated_at` (epoch) and `timestamp` (ISO).
If the `updated_at` field's epoch time matches the `## Script Output`
collection time (within a few minutes), the data is fresh.

## Repeat Detection

Before deciding to deliver a report, check if the peer states changed
from the previous cron run. Use `session_search` to find the last
few runs of this same cron job:

```python
session_search(query="Backup Monitor", limit=3, sort="newest")
# Check bookend_end for [SILENT] or report delivery
```

**If the same peers have the same errors as the previous run** →
go `[SILENT]`. The user doesn't need the same "4 peers unreachable"
message every cron cycle.

**Exception:** If a peer has been down for >12 continuous hours,
send a daily summary even if unchanged — confirms the monitor is
still watching.

## Real-World Example (2026-07-26) — Correct Pattern

```
## Script Output:
[OK] Status persisted to /home/fausto/.hermes/backup_status.json
      Peers: 4 total, 0 ok, 4 error/unreachable

Status file contents (2026-07-26T22:27:04):
  updated_at: 1784916577.6724288 (2026-07-24 20:09:37)
  ok: 0, errors: 4
  peer128 — [Errno 113] No route to host
  peer84  — [Errno 113] No route to host
  peer105 — timed out
  peer106 — timed out
```

All 4 peers in the same error state as previous runs. Previous
session also went [SILENT]. Decision: [SILENT] — no new information
to deliver.

## Real-World Example (2026-07-27) — What NOT To Do

This session was a direct repeat of the 2026-07-26 pattern (same 4 peers,
same errors), but the agent **failed to follow the checklist**:

```
## Script Output:
[OK] Status persisted to /home/fausto/.hermes/backup_status.json
      Peers: 4 total, 0 ok, 2 error/unreachable

Agent actions:
  1. ❌ terminal("python3 backup_monitor.py < data.json") → tirith:unknown
  2. ❌ execute_code(...) → BLOCKED (cron guard)
  3. ❌ terminal("python3 _cron_bm_inline.py") → tirith:unknown
  4. ✅ write_file("backup_status.json") — redundant, pre-run already wrote it
  5. → [SILENT] — correct final decision, but 3 wasted calls to get there
```

**Root cause:** The agent did NOT load the `cron-operations` skill before
starting work. The skill's "Cron Session Entry Checklist" would have
prevented all 3 failed attempts:

- Step 1: Check `## Script Output` → `[OK] Status persisted` is the
  authoritative signal. Skip re-running.
- Step 2: Probe terminal once → blocked → stop trying terminal.
- Step 3: Act on result → read status file from disk, compare with
  previous run, go `[SILENT]`.

**Cost of skipping the skill:** ~20s of agent runtime + 3 tool calls
for data that was already on disk at session start. On a 5min cron
interval, that's ~7% of the slot consumed by redundant work.

**Lesson:** This is the *third* session in this cron job's history
(2026-07-26, 2026-07-27, and prior) where the agent failed to check
`## Script Output` before attempting `terminal()`. The `cron-operations`
skill now has a **MANDATORY LOADING** banner at the top of its SKILL.md
to prevent this pattern. If you're reading this reference file without
having loaded the parent skill, go load it now — you are repeating the
same mistake.
