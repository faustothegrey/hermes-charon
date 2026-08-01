# Rebar live shadow collection preflight

Use this when Fausto asks to start live data collection for capability-reuse/Rebar on a peer.

## Preferred collection pattern

- Do **not** add inline logging in the agent/tool path when the capability-reuse plugin hook already writes `events.jsonl`; that duplicates telemetry and creates two sources of truth.
- Use a local batch analyzer scheduled as `cron no_agent` every 10–15 minutes. It should be Python stdlib, read only deltas from `~/.hermes/data/reuse-observer/events.jsonl`, and emit only anomalies or compact aggregates.
- Let peer70 aggregate daily from per-peer summaries; avoid shipping full raw logs by default.

## Peer preflight before declaring live collection ready

1. Enable the plugin explicitly:
   ```bash
   hermes plugins enable capability-reuse
   ```
2. Verify config contains the plugin and no disable override:
   ```bash
   python3 - <<'PY'
from hermes_cli.config import load_config
cfg = load_config()
print('plugins.enabled=', cfg.get('plugins', {}).get('enabled'))
print('plugins.disabled=', cfg.get('plugins', {}).get('disabled'))
PY
   ```
3. Verify a fresh PluginManager load sees the plugin and hooks:
   ```bash
   python3 - <<'PY'
from hermes_cli.plugins import PluginManager
pm = PluginManager(); pm.discover_and_load(force=True)
plug = pm._plugins.get('capability-reuse')
print('enabled', getattr(plug, 'enabled', None), 'error', getattr(plug, 'error', None))
print('hooks', {k: len(v) for k, v in pm._hooks.items() if k in ('pre_llm_call','pre_tool_call','post_tool_call')})
print('plugin_tools', sorted(pm._plugin_tool_names))
PY
   ```
   In shadow mode, `invoke_capability` should **not** appear in `plugin_tools`.
4. Confirm mode is shadow unless intentionally testing active canary:
   ```bash
   python3 - <<'PY'
import os
print(os.environ.get('CAPABILITY_REUSE_MODE', '<unset -> shadow>'))
PY
   ```
5. Run a tiny smoke turn in a **new Hermes process/session** and check `events.jsonl` grows with a `retrieval_event` whose `data.shadow_mode` is true.
6. If the gateway/HMP service was already running before the plugin was enabled, restart it before expecting gateway-originated HMP conversations to be hooked. CLI smoke in a new process proves config/plugin correctness, but long-running gateway processes need restart to pick up plugin discovery changes.

## Batch analyzer guardrails

- Maintain a cursor with inode + offset + last event id; do not rescan the full file each tick.
- Treat the last JSONL line as potentially partial; skip if it fails JSON parsing and retry next tick.
- Use `flock` or an equivalent lock to prevent overlapping cron runs on small peers.
- Report anomalies: no new events for too long, no `retrieval_event`, schema drift, plugin disabled, bad JSON beyond the trailing line.
- Keep reports redacted and aggregated: event counts, candidate counts, score buckets, session/day/peer coverage. Avoid raw prompts unless deliberately selected for human labeling and already redacted.
