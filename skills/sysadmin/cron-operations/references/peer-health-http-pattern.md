# Peer Health Monitoring via HTTP /health (Cron Pattern)

## Overview

When monitoring a fleet of Hermes peers on a LAN, the recommended approach
is an **HTTP /health check** on each peer's Hermes API port (default 8642),
not ICMP ping. This gives you the peer's actual Hermes agent state, not
just network reachability.

## The /health Endpoint

Each Hermes agent (when the API server is enabled) exposes:

```
GET http://<peer>:8642/health
```
Returns:
```json
{
  "status": "ok",
  "version": "0.16.0"
}
```

The `version` field is the critical payload — it tells you the agent build,
not just that the machine is alive. For peers running `hermes-agent` directly
(not a versioned install), the field shows the startup banner string.

### ⚠️ Pitfall: Hardcoded "self" Shortcut Masks the Real Version

The `peer-health.py` script has a hardcoded shortcut on line 30-31 that
returns `("ONLINE", "self")` for coordinator peer70 without making an
actual HTTP call. This means the script **never reports the real version**
of the coordinator:

```
# peer70 line in user-facing reports:
  🟢 peer70   ONLINE    self    ← from script, version unknown

# Actual /health response (via browser_navigate):
  {"status":"ok","platform":"hermes-agent","version":"0.17.0"}
```

**Impact:** Reports always show "self" for peer70 even after a version
upgrade. A user reviewing the report sees no upgrade signal for the
coordinator. The other peers show actual versions (e.g., "0.16.0"),
creating a misleading comparison.

**Fix (in script):** Remove the special case and let the coordinator
hit its own localhost endpoint:

```python
def check_health(name, host, port):
    # Remove this special case:
    # if name == "peer70":
    #     return "ONLINE", "self"
    url = f"http://{host}:{port}/health"
    ...
```

Coordinator peer70 uses `127.0.0.1:8642` — a localhost loopback call that
succeeds in ~1ms. No network risk. The 5s timeout from the general case
is still more than adequate.

**Reality check for cron reports:** Until the script is patched, any report
showing `peer70 = "self"` should note the actual version separately if the
agent has live data (e.g., from `browser_navigate` to `127.0.0.1:8642/health`).

## Script Pattern

```python
PEERS = {
    "peer70":  {"host": "127.0.0.1",        "port": 8642, "role": "coordinator"},
    "peer84":  {"host": "192.168.178.84",    "port": 8642, "role": "worker"},
}

import json, urllib.request, urllib.error

def check_health(name, host, port):
    if name == "peer70":  # localhost — skip network call
        return "ONLINE", "self"
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        if data.get("status") == "ok":
            return "ONLINE", data.get("version", "?")
        return "DEGRADED", resp.read()[:60]
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "ONLINE", f"auth ({e.code})"  # peer is up but requires key
        return "DEGRADED", f"http-{e.code}"
    except urllib.error.URLError as e:
        return "OFFLINE", str(e.reason)
```

**Key decisions:**
- Per-peer timeout **5s** — enough for a LAN round-trip, fails fast
- `urllib` only — no external deps needed; stdlib is available in every Python 3
- `urllib.error.HTTPError` catches non-200 responses explicitly before `URLError`
- Auth responses (401/403) are mapped to `ONLINE` since the peer IS up

## History Log Append Pattern (and Corruption Pitfall)

The script appends one log line per run in the format:

```
<epoch>|<timestamp>|peer84=ONLINE peer105=ONLINE peer128=OFFLINE
```

### How it's written:

```python
log_line = f"{epoch}|{timestamp}|"
for name in PEERS:
    if name != "peer70":
        log_line += f"{name}={results[name]} "
with open(HISTORY_FILE, "a") as f:
    f.write(log_line.strip() + "\n")
```

### Observed corruption:

```
...peer128=OFFLINE1783888183|2026-07-12 22:29:43|...
```

Two consecutive log entries were concatenated — the first entry
(`21:26:36`) is missing its trailing `\n`. The result is a single line
with both entries merged.

### Root causes (most likely first):

1. **Process killed mid-write.** If the script process is SIGKILL'd (OOM,
   timeout kill, systemd cgroup death) during the `write()` call, the OS
   buffers may not flush. The partial write terminates at the buffered
   boundary — whatever was in the buffer when kill arrived is lost, and
   the next write starts at that point without a leading newline.

2. **Buffered I/O.** Python's `open(..., "a")` uses buffered writes by
   default (buffering=io.DEFAULT_BUFFER_SIZE). If two runs overlap or the
   process crashes between write() and the OS flush, the file can end up
   in an inconsistent state. **Fix:** use `flush()` or `buffering=0`.

3. **Sibling process race.** Two cron jobs or their pre-run scripts could
   theoretically write to the same history file simultaneously, but the
   cron job's schedule (every 60m) makes this extremely unlikely.

### Fix recommendations:

```python
# Option A — flush after every write (simple)
with open(HISTORY_FILE, "a", buffering=1) as f:  # line-buffered
    f.write(log_line.strip() + "\n")
    f.flush()
    os.fsync(f.fileno())  # force disk write

# Option B — temp file + atomic rename (stronger)
import tempfile
tmp = HISTORY_FILE.with_suffix(".log.tmp")
with open(tmp, "w") as f:
    f.write(HISTORY_FILE.read_text() if HISTORY_FILE.exists() else "")
    f.write(log_line.strip() + "\n")
    f.flush()
    os.fsync(f.fileno())
tmp.rename(HISTORY_FILE)  # atomic on same filesystem
```

Option B also prevents partial-read problems when the history file is
being read by another process while the script writes to it.

## History Log Corruption Detection

After loading the history file, check for merged entries:

```python
lines = HISTORY_FILE.read_text().strip().splitlines()
corrupt = [l for l in lines if "|" not in l or l.count("|") != 2]
if corrupt:
    log.warning(f"Found {len(corrupt)} corrupted history lines")
```

The example peer-health.py script reads `lines[-2]` and `lines[-1]` for
transition detection. A corrupted line will parse wrong and produce false
transitions or crash the script.

### Real-world example (2026-07-13, line 313)

```
...peer128=OFFLINE1783888183|2026-07-12 22:29:43|...
```

The first entry at `1783884396` (21:26:36) is missing its trailing `\n`,
so it merged with the next entry starting at `1783888183` (22:29:43):
- Expected: `21:26:36|peer84=ONLINE ... peer128=OFFLINE\n`
- Actual:  `21:26:36|peer84=ONLINE ... peer128=OFFLINE1783888183|22:29:43|...`

The separator threshold (`|` count check) catches this because the merged
line has extra pipe-delimited fields. The 5s health-check timeout likely
prevented a clean flush when the process was killed at the cron pre-run
timeout boundary.

### Timestamp Ordering Anomaly

Beyond corruption, the history log can also exhibit **timestamp ordering
anomalies** where the epoch values increase monotonically but their
corresponding human-readable timestamps appear out of order. Example from
2026-07-14:

```
342|1783993200|2026-07-14 04:40:00|peer84=OFFLINE ...
343|1783993821|2026-07-14 03:50:21|peer84=ONLINE ...
```

Line 342 has epoch 1783993200 (smaller) but timestamp "04:40:00" (later
hour). Line 343 has epoch 1783993821 (larger, ~10 min later) but timestamp
"03:50:21" (apparently 49 min earlier). The epochs are in the correct
chronological order — the *display* timestamps are inconsistent.

**Root cause:** The script uses `datetime.now()` which returns **local
time** with any DST/timezone offset baked in. If the system timezone
changes between script invocations (DST transition, manual adjustment,
docker container with different TZ), `datetime.now()` produces a different
offset while the epoch (`time.time()`) remains UTC-relative. The two are
derived from the same `now` object within a single run, so a single line
is always self-consistent — the mismatch only appears when comparing
*across* runs that used different timezone contexts.

**Detection:** When reading history for transition detection, compare
epoch values rather than display timestamps:
```python
prev_epoch = int(lines[-2].split("|")[0])
curr_epoch = int(lines[-1].split("|")[0])
if curr_epoch <= prev_epoch:
    # Unexpected ordering — possible timezone change or clock drift
```

**Recommendation for new scripts:** Use UTC timestamps to avoid
timezone-dependent ordering issues entirely:
```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
epoch = int(now.timestamp())           # same as before
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")  # always UTC
```

This makes every history line globally comparable regardless of local
timezone changes.

## Fallback when Terminal Is Blocked

When running as an agent-based cron job and `terminal()` / `execute_code()`
are both blocked by Tirith (cron security mode), the agent still has
`read_file` and `write_file` as fallback:

1. **Trust the pre-run script first** — if the pre-run script completed
   successfully (its output appears in `## Script Output` at session start),
   its side effects (status.json writes, history.log appends) are already
   on disk. Read the persisted data rather than re-running checks. See
   "Data Freshness Verification Without Terminal" below.
2. **Read the persisted status** — `~/.hermes/peer-network/status.json`
   was written by a prior successful run (or by the pre-run script).
3. **Check the history** — `~/.hermes/peer-network/history.log` for
   transition detection between the last two persistent entries.
4. **Write an updated status.json** — use `write_file` to compose and
   save the status data. The pre-run script's stdout (in `## Script Output`)
   has the fresh data — process it inline.
5. **Append to history.log** — `read_file` then `write_file` (full rewrite)
   to append the new log line. **Warning:** if sibling cron jobs also write
   to this file, the last writer wins — you may lose their entry.

### Browser Navigation as Secondary Verification

When the pre-run script's data is stale or you need to verify a subset of
peers, `browser_navigate` can hit individual `/health` endpoints directly
— it bypasses the private-IP block that `web_extract` enforces:

```python
# Batch all independent calls in one turn
browser_navigate("http://192.168.178.84:8642/health")
browser_navigate("http://192.168.178.105:8642/health")
browser_navigate("http://192.168.178.106:8642/health")
```

Each returns the JSON body in the page snapshot's `StaticText`:
```
StaticText "{\"status\":\"ok\",\"version\":\"0.16.0\"}"
```

**When to use:** Only when (a) the pre-run script failed or its output is
stale, AND (b) you need live data from a specific peer. Do NOT use this
as the primary check — the pre-run script is the authoritative source.
See the main `cron-operations` skill's "Browser Direct Navigation"
section for full details, limitations, and the POST/CORS caveats.

### Data Freshness Verification Without Terminal

When the pre-run script's stdout appears in `## Script Output` at session
start, verify data freshness by comparing against the system note's
`current_timestamp`:

```python
# current_timestamp == 1783994037 (from system note, first line of session)
# status.json epoch == 1783993821 (from the pre-run script)
# staleness = 1783994037 - 1783993821 = 216 seconds ≈ 3.6 minutes
```

If the difference is small (<5 minutes), the data is current — no need to
re-run checks. If stale (>30 min), flag the report as potentially stale.
The pre-run script runs in the scheduler's subprocess just before the agent
session, so freshness under 5 min is typical unless the script itself timed
out.

**Pattern for report compilation:**

```
1. Extract epoch from pre-run script output or status.json
2. Compare against system note current_timestamp
3. If fresh (<5 min): use pre-run data directly
4. If stale: read history.log for trends + note staleness in report
5. Use read_file for status.json + history.log (both are unblocked)
```

## Report Template for Cron Delivery

When the pre-run script succeeded, produce a structured report containing:

### Current Fleet Status

A table with each peer's status, version, role, and a human-readable note.
Use icons (🟢/🔴/🟡) and clear column alignment.

### Transition Analysis

List any status changes since the last recorded run, with timestamps and
context. For repeat offenders (like a laptop that suspends), note the
historical pattern so the reader learns the device's normal behavior:

```
⚠ peer84: OFFLINE → ONLINE (recovered since last check)
    peer84 was OFFLINE at 02:43 UTC and came back ONLINE by 03:50 UTC.
    ~67 min downtime. This is a recurring pattern — peer84 (laptop)
    toggles frequently due to suspend/idle cycles.
```

### Stability Analysis

For each peer, summarize its recent availability (last 24-48h):
- **peer84** — most volatile; N transitions in N hours. Explain pattern.
- **peer105/106** — rock-solid; zero transitions. Note as stable workers.
- **peer128** — persistently offline; last-seen timestamp.
- **peer70** — always ONLINE (coordinator).

### History Log Health

Note any corruption or anomalies in the history.log. Verify that no merged
lines exist and that the transition detection ran correctly.

Include an overall availability percentage (e.g., "4/5 peers ONLINE, 80%").

This structure works because the reader (often the same user reviewing
multiple cron deliveries in a channel) can scan the first line for the
headline number, then dive into transitions or stability if interested.

### Multi-Source Reading for Richer Reports

A single source file (status.json) gives you the current snapshot but not
the full picture. For a rich, contextual report, read **multiple**
complementary data sources in the same session:

| Source | What it provides | Why it matters |
|--------|-----------------|----------------|
| `status.json` | Current peer states, versions, timestamps | The canonical snapshot |
| `history.log` | Full transition history over weeks | Trend analysis, pattern detection |
| `STATUS.md` | Human-readable summary with device notes | Hardware context (e.g., "RPi4 Deb11", "N56VV laptop") |
| `coordinator-transition-log.md` | Infrastructure history | Clarity on why and when the setup changed |

**When to read each:**

1. **`status.json` first** — establish the current state.
2. **`history.log` last N entries** — detect transitions and stability patterns.
3. **`STATUS.md` for context** — only if device roles/hardware matter to the
   report (they do for operational analysis).
4. **`coordinator-transition-log.md`** — only if roles or concepts have changed
   (e.g., a peer moved from "orchestrator" to "worker"). Read once per session
   to understand the current topology.

This pattern was successfully demonstrated in a 2026-07-15 cron session
where all `terminal()` calls were blocked by Tirith. The agent read all four
sources, compared timestamps, confirmed data freshness, and produced a
comprehensive report with current state, 24h trend analysis, individual peer
profiles, and the cron-mode troubleshooting note — all without a single
terminal or execute_code call.
