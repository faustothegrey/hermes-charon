# HERMES_EXEC_ASK Bleed Into Cron Sessions — Root Cause Diagnostic

## The Bug

When the Hermes gateway is running (which it always is for production cron
deployments), `gateway/run.py:1638` sets:

```python
os.environ["HERMES_EXEC_ASK"] = "1"
```

This env var is **process-global** — every subprocess, thread, and cron
scheduler job spawned by the gateway process inherits it.

## Why It Breaks Cron

The approval flow in `tools/approval.py` has two paths:

1. **Cron path** (line 1613-1630): Short-circuits when `not is_cli AND
   not is_gateway AND not is_ask`. Returns `{"approved": True}` for
   non-dangerous commands — Tirith is NEVER reached.

2. **Gateway/ask path** (lines 1636+): Runs Tirith, then prompts the
   user for approval via the gateway queue.

The check at line 1613:

```python
if not is_cli and not is_gateway and not is_ask:
    # Cron handling...
    return {"approved": True}
```

Where:
- `is_cli = env_var_enabled("HERMES_INTERACTIVE")` → **False** ✓
- `is_gateway = _is_gateway_approval_context()` → checks HERMES_CRON_SESSION
  first (line 150), returns **False** ✓
- `is_ask = env_var_enabled("HERMES_EXEC_ASK")` → **TRUE** ✗ **— bled from
  the gateway process!**

Because `is_ask` is True, the condition at line 1613 is **not entered**.
The code falls through to the gateway path (line 1636+), which runs Tirith,
finds the `tirith:unknown` pattern, and returns `{"status": "pending_approval"}`
with no user present to approve it.

## Why `cron_config_override.yaml` Doesn't Help

The override file's `approvals.cron_mode: allow` is set correctly, but it
never gets a chance to apply because **the cron path itself is skipped**
when `HERMES_EXEC_ASK` is set. The override operates within the cron path
(deciding whether to block or approve dangerous commands there), but that
path is never reached.

This explains the empiric observation from
`cron-config-override-pitfall.md`: even `cron_mode: allow + mode: off` in
the override file did not unblock terminal commands.

## Two Possible Fixes

### Fix 1: Fix `check_all_command_guards` to check both env vars

In `tools/approval.py`, line 1613 should also check for cron context:

```python
# Current (broken):
if not is_cli and not is_gateway and not is_ask:

# Fixed — also short-circuit when HERMES_CRON_SESSION is set:
if not is_cli and not is_gateway and not is_ask or env_var_enabled("HERMES_CRON_SESSION"):
```

This preserves the intent: cron sessions always take the cron path
regardless of other env var bleed.

### Fix 2: Unset `HERMES_EXEC_ASK` in the cron scheduler

In `cron/scheduler.py`, after the `HERMES_CRON_SESSION` set at line 2160:

```python
os.environ["HERMES_CRON_SESSION"] = "1"
os.environ.pop("HERMES_EXEC_ASK", None)  # prevent gateway bleed
```

This is a surgical fix — it only affects cron job execution contexts.

## How I Found This

1. Terminal command `python3 ~/.hermes/scripts/lan-monitor.py` blocked with
   `pattern_key: "tirith:unknown"` and `status: "pending_approval"`.

2. Traced the approval flow through `tools/approval.py`:
   - `check_all_command_guards()` → line 1613 short-circuit check
   - `_is_gateway_approval_context()` → correctly returns False (checks
     HERMES_CRON_SESSION first at line 150)
   - But `is_ask` was True — the only external env var that could bypass
     the cron path

3. Searched for `HERMES_EXEC_ASK` in the codebase:
   - `gateway/run.py:1638` — set unconditionally at import time
   - `tui_gateway/server.py:1848` — also set in the TUI gateway
   - Nowhere in `cron/scheduler.py` is it unset

4. Confirmed the fix by understanding that `no_agent: true` cron jobs
   bypass the agent entirely, so the HERMES_EXEC_ASK env var never
   affects them.

## Affected Cron Jobs

Any agent-based cron job (`no_agent: false`) running inside the gateway
process that needs to execute `terminal()` or `execute_code()` commands.

**Symptoms:**
- Every `terminal()` call fails with `tirith:unknown` + `approval_pending`
- Every `execute_code()` call fails with the cron block message
- Setting `approvals.cron_mode: allow` in the override file has no effect
- `no_agent: true` jobs with a `script` field work fine

## Workarounds (in Order of Reliability)

| Workaround | How | Caveat |
|---|---|---|
| **Convert to `no_agent: true`** | Set `script: my_script.py` in jobs.json | Script must be self-contained; no LLM reasoning |
| **Add `approvals` to main config.yaml** | `cron_mode: allow` in `~/.hermes/config.yaml` | User must do this from interactive session; agent can't mid-session |
| **Fix the code** | Either Fix 1 (approval.py) or Fix 2 (scheduler.py) above | Requires code change and restart |
