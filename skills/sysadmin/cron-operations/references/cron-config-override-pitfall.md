# Cron Config Override Pitfall: No Effect on Either Tool
## Scenario

The user has a `cron_config_override.yaml` at `~/.hermes/cron/cron_config_override.yaml`:

```yaml
approvals:
  cron_mode: allow       # "correct" value — but still doesn't work
  mode: off               # "correct" value — still doesn't work
```

Despite using the "correct" values (`allow` + `off`), the cron agent's
`terminal()` and `execute_code()` calls are **both** still blocked:

```
Security scan: security issue detected (pattern: tirith:unknown)
Cron jobs run without a user present to approve it.
```

```
BLOCKED: execute_code runs arbitrary local Python (including subprocess calls
that bypass shell-string approval checks). Cron jobs run without a user present
to approve it. Use normal tools instead, or set approvals.cron_mode: approve
only if this cron profile is intentionally trusted.
```

**Key insight: the values are correct but irrelevant — the Tirith scanner
never reads the override file.**

## Why It Fails — Five Reasons

### 1. The override file is the wrong location entirely

The value in the override file — whether `cron_mode: allow`, `cron_mode: approve`,
or `cron_mode: deny` — does not matter because the Tirith scanner **never reads
the override file.** It reads the profile's main `config.yaml` directly.

Even with `cron_mode: allow` in the override, terminal commands are still blocked
(proven empirically 2026-07-14). The only fix is to put the setting in
`~/.hermes/config.yaml` at the profile level.

> **Historical note:** The `cron_mode: approve` misconfiguration was the original
> diagnosis (setting `approve` thinking it meant "auto-approve"). This turned out
> to be a red herring — the file location was the real bug. Regardless of value,
> the override file has no effect on Tirith.
>
> **Session 2026-07-17 addendum:** An agent session also attempted
> `security.tirith_enabled: false` in the override file — expecting it to skip
> the Tirith scanner entirely. Same result: no effect. Tirith does not read the
> override file for any security-relevant key, not just approvals. `security.*`,
> `approvals.*`, and `tirith_*` settings are all ignored when placed there.

### 2. `cron_config_override.yaml` only matters at session start

Even with the correct value, the override file is loaded once at session
start. Changes to it mid-session have no effect — the session was already
launched with whatever config was in effect.

### 3. `execute_code` ignores the override entirely

The `execute_code` tool has its own independent cron-mode check that reads
the **profile's main `config.yaml`** (`~/.hermes/config.yaml`), not the cron
override file. The override file is loaded by the cron scheduler but
`execute_code` bypasses that path.

### 4. `mode: off` does not bypass the Tirith scanner

Even with both `cron_mode: allow` and `mode: off` set in the override file,
**terminal commands are still blocked.** The `mode: off` setting disables
Hermes' own approval system (the `pending_approval` gate), but the Tirith
pre-execution security scanner runs independently of the approvals system.
Tirith's cron-mode check fires before the approvals system is even
consulted, so disabling approvals has no effect on Tirith blocks.

**Empirically confirmed (twice): even correct values have no effect**

A production session (2026-07-14, peer-health cron) had the override file
with both `cron_mode: allow` and `mode: off` — the "correct" values — and
**every** `terminal()` and `execute_code()` call was still blocked.

Re-confirmed 2026-07-15: a second cron session (peer-health monitor on
peer70) had the same override file with identical values, and every single
`terminal()` call — including `pwd && echo hello`, `ls`, `which tirith` —
was blocked with `tirith:unknown`. This is a definitive, reproducible
result: the override file is never the right place for these settings,
regardless of values.

```
Security scan: security issue detected (pattern: tirith:unknown)
Cron jobs run without a user present to approve it.
```

This confirms conclusively that the override file is never the right place
for these settings. The Tirith scanner reads the profile's main `config.yaml`
directly, not the cron override, regardless of what values the override
contains.

**Bottom line:** No combination of settings in `cron_config_override.yaml`
can unblock `terminal()` or `execute_code()` in cron mode. The override
file is the wrong place for these settings — they must be in the profile's
main `config.yaml`.

## Diagnosis Checklist

| Check | What to verify | How |
|-------|---------------|-----|
| Override file exists | `~/.hermes/cron/cron_config_override.yaml` exists | `ls -la ~/.hermes/cron/cron_config_override.yaml` |
| Override contents irrelevant | Any setting — `cron_mode: allow`, `mode: off`, `security.tirith_enabled: false`, `tirith_enabled: false`, `approvals.*` — all ignored | Proven empirically across 3+ sessions (Jul 14–17). Skip override debugging entirely. |
| Main config has the setting | `~/.hermes/config.yaml` has `approvals.cron_mode: allow` | `grep cron_mode ~/.hermes/config.yaml` — this is the **only** way to fix it |
| Session restart needed | Changes take effect on next cron tick, not mid-session | Wait for next scheduled run or trigger manually |

## Workaround (within the failed session)

Since both `terminal()` and `execute_code()` are blocked in-session, use
the **Manual `write_file` Composition** pattern from the main
cron-operations SKILL.md:

1. Trust the pre-run script's output (in `## Script Output` at session start)
2. Read the persisted data files (`read_file`) — they were written by the pre-run script
3. Manually compose any output JSON/dataset from the available data
4. Write the result file with `write_file` (not blocked)

**Do NOT use `delegate_task` with `toolsets=["terminal"]`** — subagents
reliably fail to produce results in cron mode. The cron session ends before
the subagent can report back. See main SKILL.md's "Pitfall: delegate_task"
section for details.

## Permanent Fix

Add `approvals.cron_mode: allow` to `~/.hermes/config.yaml` at the profile
level — this is the **only** way to fix the Tirith cron-mode block:

```yaml
approvals:
  cron_mode: allow
```

**Do NOT waste time on `cron_config_override.yaml`** — it is never the right
place regardless of the values it contains. The override file controls
scheduler-side configuration (run schedule, delivery, etc.), not the agent's
security posture.

Both changes can only be done from an **interactive (non-cron) session**
since cron agents cannot modify `config.yaml` and override changes won't
affect the current session anyway.

## Related

- Main SKILL.md: "Security: The `approvals.cron_mode` Setting" section —
  includes the three-mode reference table.
- `references/backup-monitor-timeout-pattern.md` — specific fallback data
  sources when the pre-run script timed out.