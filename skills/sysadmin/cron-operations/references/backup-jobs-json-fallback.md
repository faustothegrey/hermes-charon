# Backup `jobs.json` as Fallback Data Source

When terminal() is completely blocked by Tirith in cron mode, the backup cron config at `~/.hermes/Backups/hermes-config/cron/jobs.json` serves as an authoritative SNAPSHOT of all registered cron jobs — their IDs, names, scripts, schedules, completion counts, last status, and execution history.

## Why This Works

The backup is created periodically by `hermes-config-backup-nightly.sh` (or manually via `hermes config backup`). It contains the **complete cron scheduler state** serialized at backup time. Unlike `session_search` (which only finds sessions that went through the FTS5 database with varying recall quality), the backup `jobs.json` has:

- Every job's `id`, `name`, `schedule`, `script`, `no_agent` flag
- `last_status` and `last_error` for each job
- `completed` count (total runs)
- `next_run_at` and `last_run_at` timestamps

## When to Use

| Terminal state | Best source | Why |
|---|---|---|
| **Blocked** (`tirith:unknown`) | Backup `jobs.json` | The backup has complete data. Only stale by ~1-24h depending on backup frequency. |
| **Blocked** | `session_search` (by job name) | Catches recent cron runs the backup may not have. Complementary to backup. |
| **Working** | `hermes cron list` via terminal | Live, authoritative, current. Only ~2s. |

## Cross-Referencing Pattern: User Claims vs Actual Jobs

When a user reports cron job overlaps to investigate, their analysis may have factual errors. The backup `jobs.json` is the ground truth to validate against.

### Step-by-step

1. **Read the backup:**
   ```
   read_file("~/.hermes/Backups/hermes-config/cron/jobs.json")
   ```
   The file is large (~700+ lines). Focus on extracting: job name, schedule, script, completed count, last_status.

2. **Build a coverage matrix** structured by schedule frequency:

   ```
   Freq     | Jobs at that freq
   ─────────┼─────────────────────────────────────
   every 1m | guardiano-peer70 watchdog (10475 runs)
   every 2m | peer128 keepalive (3767 runs, ERROR)
   every 3m | HMP Watchdog (207 runs)
   every 5m | peer70-watchdog (165), peer-health-watch (165), Load Monitor (1639)
   every 10m| lan-monitor (89)
   every 30m| backup-monitor (354)
   every 60m| 4 jobs + HMP Healthcheck orario (hourly)
   ```

3. **Cross-reference each user-claimed job against the matrix:**

   | User says | Actual | Discrepancy |
   |-----------|--------|-------------|
   | `peer-queue-delivery` (2m) | ❌ Non esiste | likely confused with `guardiano-peer70 watchdog` (1m) or `peer128 keepalive` (2m) |
   | `hmp-ping-round.py` (10m) | ❌ Non esiste | Actual: `hmp-healthcheck-ping.py` runs hourly, not 10m |
   | `peer70-watchdog` (5m) + `peer-health-watch` (5m) | ✅ Confermato | MA manca `Load Monitor` (5m) — terzo job |
   | `peer-queue-delivery` + `HMP Watchdog` | ❌ Base inesistente | `peer-queue-delivery` non esiste, quindi overlap #4 è infondato |

4. **Report the corrected assessment** — flag each discrepancy, confirm what's real, and note anything the user missed entirely.

## Real-World Example

See cron job session 2026-07-18 (cron_34c92c320db0_20260718_114112 on peer70). The user reported 4 overlap pairs. Cross-referencing against `Backups/hermes-config/cron/jobs.json` revealed:

- **2 jobs confirmed** exactly as the user described
- **2 jobs don't exist** on this system at all (phantom jobs from a different peer or confusion)
- **1 unmentioned job** at the same frequency (Load Monitor at 5m)
- **1 misidentified frequency** (hmp-healthcheck-ping.py runs hourly, not every 10m)

Without the backup jobs.json, verifying these claims would have required terminal access to run `hermes cron list` — which was blocked by Tirith.

## Data Freshness Tradeoff

The backup jobs.json is ASYNCHRONOUS — it may be minutes to hours stale. For most cron audit use cases this is acceptable because:

- Job registration is infrequent (hours/days between changes)
- Job schedules are stable (you're auditing existing patterns, not current-second state)
- `last_status` and `last_run_at` may be slightly behind, but `completed` counts are cumulative and reliable

If you need current-second accuracy and terminal is blocked, fall back to `browser_navigate` for individual peer health checks, but accept that the full cron job list requires terminal access or the backup.
