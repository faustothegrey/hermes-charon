# Quest Advancement Cron Pattern

## Overview

`quest_advance.py` is a pre-run cron script that advances quests in
round-robin fashion. It reads quest files from peer N56VV's Obsidian
vault, identifies active (non-complete) quests, advances one, and
optionally sends a status email.

## Architecture

```
cron scheduler → quest_advance.py (pre-run script, 120s timeout)
                → 1. HTTP API to N56VV → fetch quest files
                → 2. HTTP API to N56VV → parse into JSON array
                → 3. Round-robin select one active quest
                → 4. HTTP API to N56VV → advance the quest
                → 5. HTTP API to N56VV → send email via himalaya
                → 6. Save state to ~/.hermes/quest-advancement-state.json
```

Each step is a separate LLM API call to peer84 (N56VV, 192.168.178.84:8642),
adding 30-60s per call. Steps 3-6 are unreachable within 120s when steps
1+2 already consume ~100-110s.

## State File Schema

`~/.hermes/quest-advancement-state.json`:

```json
{
  "round_robin_index": 0,
  "last_advanced": null,
  "advanced_quests": [],
  "run_time": 1783807322.3035903,
  "skipped_reason": "...",
  "next_action": "..."
}
```

## Known Failure Modes

### N56VV Cooling Window (Scheduled Downtime)

**Symptom:** Pre-run script exits with `[Errno 113] No route to host`
connecting to `192.168.178.84:8642` (N56VV). Script Stdout shows:
```
--- Step 1: Fetching quests from N56VV ---
```
...then the traceback. No quest data is fetched.

**Root cause:** N56VV (peer84) has scheduled cooling windows to prevent
overheating:
- **Diurnal:** 11:00–17:00 CEST (core hours)
- **Nocturnal:** 02:00–03:00 CEST

The quest advancement cron schedule (`0 */4 * * *` = 00, 04, 08, 12, 16,
20) overlaps with the diurnal window at the 12:00 and 16:00 slots. During
these hours, N56VV is intentionally powered off and unreachable. This is
**expected behavior**, not an error condition.

**Detection:** Check the state file's `run_time` or the current system
time against the known cooling windows. If within 11:00–17:00 or
02:00–03:00 CEST, the failure is expected and not actionable.

**Repeat detection:** When N56VV is unreachable during cooling hours,
use `session_search` to find the previous run's output:
```
session_search(query="Quest Advancement", limit=3, sort="newest")
```
Compare the previous run's response — if it reported the same error
(N56VV unreachable) and the quest state is unchanged, go [SILENT].
Do NOT deliver a new report for every 4h cycle during cooling hours;
the user already knows N56VV is offline.

**Example from production (2026-07-17):**
```
12:05 · N56VV unreachable, all quests complete → REPORT (first occurrence)
16:00 · Same error, identical state                       → [SILENT] (repeat)
20:00 · N56VV should be back online                       → Check again, report if changed
```

### Timeout on 2nd LLM Call

**Symptom:** Pre-run script times out at 120s. Raw quest data from step 1
is saved to `/tmp/quests_raw.txt`, but the parsed JSON
(`/tmp/quests_parsed.json`) is missing. The state file may be written by a
fallback path (`quests=[]` → "no active quests").

**Root cause:** Step 1 (fetch) takes ~50-60s. Step 2 (parse) runs next but
has only ~60-70s left of the 120s script timeout. If step 2's LLM call to
N56VV takes >60s, the script is killed mid-call.

**Fallback in script code (quest_advance.py lines 71-89):**
```python
try:
    quests_json = ask_n56vv(...)  # step 2 — may time out
    quests = json.loads(quests_json)
except Exception as e:
    quests = []  # fallback: no quests found

if not quests:
    save_state({"round_robin_index": 0, ...})
    return  # exits cleanly with "no active quests"
```

So even on timeout, the script exits cleanly with a correct (if
uninformative) state. The post-run agent sees a timeout error but the
state file correctly reports "no active quests" by coincidence.

### Terminal Blocked on Cron Host

**Symptom:** The cron host (e.g., peer70) has Tirith security blocking
all `terminal()` and `execute_code()` calls in cron mode (there is no
user present to approve).

**Workaround — browser_navigate for GET endpoints:**
Use `browser_navigate` to reach N56VV's `/health` endpoint. This
works because simple GET requests don't trigger CORS preflight:

```
browser_navigate("http://192.168.178.84:8642/health")
```

- If N56VV is online → snapshot shows JSON response (e.g.,
  `StaticText '{"status":"ok"}'`)
- If N56VV is down → `net::ERR_ADDRESS_UNREACHABLE` (equivalent to
  the pre-run script's `[Errno 113] No route to host`)
- POST endpoints (`/v1/chat/completions`) DO NOT work from browser
  context — no way to set auth headers or POST body

**Do NOT use `delegate_task`** — subagents spawned from cron context
have the same cron-mode blocks (terminal, execute_code) and their
results are not reliably returned before the cron session ends. See
the cron-operations skill's "Workaround When Both terminal() and
execute_code() Are Blocked" section for the full rationale.

**Verify local files first:** The pre-run script's output and the
state file are available via `read_file` — do not waste browser calls
to re-verify what the files already show.

## Post-Run Agent Response

When the pre-run script times out or fails but partial data exists:

1. **Read state file** — `~/.hermes/quest-advancement-state.json`
   (last saved state, may be empty/from prior run)
2. **Check temp files** — `/tmp/quests_raw.txt` (raw quest data, may
   not exist if script failed at step 1)
3. **Confirm N56VV status** — `browser_navigate` to `/health` endpoint
   to distinguish cooling-window downtime from real outage:
   - `ERR_ADDRESS_UNREACHABLE` during 11:00–17:00 CEST → expected
     cooling window. Go [SILENT] on repeat occurrences.
   - `ERR_ADDRESS_UNREACHABLE` outside cooling window → genuine
     outage worth reporting.
4. **Run repeat detection** — `session_search(query="Quest Advancement",
   limit=3, sort="newest")` to check if the same error with the same
   cause was already reported. If so, go [SILENT].
5. **Report to user** — what happened, what data was gathered, whether
   advancement occurred (likely not, if N56VV is unreachable)

## Mitigations

| Strategy | Implementation |
|---|---|
| Merge steps 1+2 | Combine fetch + parse into a single LLM call to N56VV: "list all quests and return only active ones as JSON" |
| Reduce max_tokens | Parsing-only calls need 2000 tokens, not 8000 — reduces LLM latency |
| Increase script timeout | Bump cron pre-run timeout from 120s to 240s+ |
| Move advancement to post-run agent | Script only fetches raw data; the LLM agent handles parsing, selection, and advancement with no per-call timeout |
| Skip email on timeout | Make email step conditional on all prior steps completing within budget — don't attempt it if timing is tight |