# Cohort verification recipe (post-distribution)

How to verify a capability-reuse release actually went live after
distribution, and how to read the event log correctly.

## Where the events live

- Log: `~/.hermes/data/reuse-observer/events.jsonl` (append-only JSONL)
- **Plugin version is in `data.plugin_version`, NOT top-level.** Top-level
  keys are `event_id, event_type, schema_version, timestamp, seq, data`.
  Reading `e.get("plugin_version")` returns None — always go
  `e["data"].get("plugin_version")`. (First diagnosis of this cost several
  wrong reads on 2026-08-14.)

## Quick cohort count

```python
import json, collections
c = collections.Counter()
with open("/home/fausto/.hermes/data/reuse-observer/events.jsonl") as f:
    for line in f:
        e = json.loads(line)
        c[str(e["data"].get("plugin_version", "?"))] += 1
print(dict(c))
```

## Interpreting the numbers

- `included: 0` for the new version right after distribution is EXPECTED —
  events of the new version only start flowing after the gateway is
  restarted (the plugin is loaded in memory at startup).
- After restart, new-version events carry `schema_version: 1.3` with
  `data.producer` populated; legacy events are schema 1.2.
- Residual OLD-version events with recent timestamps AFTER the restart are
  NOT from the gateway — they come from a separate process running an older
  plugin in memory (e.g. a stray `hermes` CLI session). Check
  `ps aux | grep hermes` and compare process start time vs plugin mtime.

## Verify the running gateway actually has the new plugin

Compare timestamps:
- `ls -la ~/.hermes/plugins/capability-reuse/plugin.yaml` (bump time)
- `systemctl --user status hermes-gateway.service` → "Active: ... since" (start time)

If the gateway started AFTER the plugin bump, the new version is loaded —
no restart needed. The HMP agent-card (`/hmp/agent-card`) reports the HMP
plugin version (0.1.x), NOT the capability-reuse version; don't use it for
this check.

## Workflow note (Fausto)

Before applying any new fix to the hermes-agent repo, commit outstanding
capability-reuse code changes first ("per prima cosa committa tutto") —
revertible steps, stable-operation-first. Uncommitted harness-feedback
plumbing (plugins.py / tool_executor.py / gateway/run.py / model_tools.py)
and the fix commit should land as separate commits (feat vs fix).
