# Phase 1B peer128 canary and peer70 synchronization notes — 2026-07-27

Use this when continuing capability-reuse Phase 1B active canary work across LAN peers.

## Durable lessons

- Fausto prefers peer128 as the canary/test target for capability-reuse/HMP tests. Do not default to peer70 as the target unless explicitly asked; peer70 is often the orchestrator or central repository coordinator.
- Keep the distinction explicit:
  - host under test = machine whose Hermes runtime/plugin is being tested
  - HMP target = peer being probed by `hmp-healthcheck`
  A successful healthcheck of peer128 from peer106 does not prove peer128 has the plugin installed.
- When deploying to peer128 via peer70, sync both:
  - plugin files to `~/.hermes/plugins/capability-reuse/`
  - registry data to `~/.hermes/data/capability-registry/{registry.json,contracts/}`
  The plugin import can succeed while retrieval fails if registry data is missing.
- peer128 uses macOS system `python3` 3.9 in some direct smoke paths. Keep plugin source Python 3.9-compatible; if using modern annotations such as `list[str] | None`, include `from __future__ import annotations` at the top of plugin `.py` files.
- The active canary should remain limited to read-only `hmp-healthcheck@1.0.0`. Do not enable mutating `hmp-send` without idempotency/duplicate-send policy and manual review controls.

## Peer70 synchronization pattern

1. Package current plugin source from the working node:

```bash
tar -C ~/.hermes/skills/hermes/capability-reuse/plugin --exclude='__pycache__' -czf /tmp/capability-reuse-plugin.tgz .
```

2. Copy to peer70 and unpack into both its central repo and runtime plugin directory:

```bash
scp /tmp/capability-reuse-plugin.tgz fausto@192.168.178.70:/tmp/capability-reuse-plugin.tgz
ssh fausto@192.168.178.70 '
  mkdir -p ~/.hermes/skills/hermes/capability-reuse/plugin ~/.hermes/plugins/capability-reuse
  tar -xzf /tmp/capability-reuse-plugin.tgz -C ~/.hermes/skills/hermes/capability-reuse/plugin
  tar -xzf /tmp/capability-reuse-plugin.tgz -C ~/.hermes/plugins/capability-reuse
'
```

3. From peer70, deploy to peer128:

```bash
ssh fausto@192.168.178.70 '
  tar -C ~/.hermes/skills/hermes/capability-reuse/plugin --exclude=__pycache__ -czf /tmp/capability-reuse-plugin-from-peer70.tgz .
  scp /tmp/capability-reuse-plugin-from-peer70.tgz fausto@192.168.178.112:/tmp/capability-reuse-plugin-from-peer70.tgz
  ssh fausto@192.168.178.112 "mkdir -p ~/.hermes/plugins/capability-reuse && tar -xzf /tmp/capability-reuse-plugin-from-peer70.tgz -C ~/.hermes/plugins/capability-reuse"
'
```

4. Sync registry data if peer128 lacks it:

```bash
tar -C ~/.hermes/data/capability-registry -czf /tmp/capability-registry.tgz registry.json contracts
scp /tmp/capability-registry.tgz fausto@192.168.178.70:/tmp/capability-registry.tgz
ssh fausto@192.168.178.70 '
  scp /tmp/capability-registry.tgz fausto@192.168.178.112:/tmp/capability-registry.tgz
  ssh fausto@192.168.178.112 "mkdir -p ~/.hermes/data/capability-registry && tar -xzf /tmp/capability-registry.tgz -C ~/.hermes/data/capability-registry"
'
```

5. Ensure peer128 config has one `capability-reuse` entry in `plugins.enabled`. Remove duplicates if a previous deploy inserted it twice.

6. Restart peer128 gateway through peer70 when needed:

```bash
ssh fausto@192.168.178.70 'ssh fausto@192.168.178.112 "launchctl kickstart -kp gui/$(id -u)/homebrew.mxcl.hermes-gateway 2>/dev/null || launchctl kickstart -kp gui/$(id -u)/hermes-gateway 2>/dev/null || true"'
```

7. Verify peer128 health:

```bash
curl -sS --connect-timeout 3 --max-time 8 http://192.168.178.112:18643/hmp/health
```

Expected example:

```json
{"status":"ok","service":"hmp-gateway","gateway_adapter":true,"node_id":"peer128","bind":"0.0.0.0:18643"}
```

## Peer128 smoke checks

Run a direct Python smoke script on peer128 via peer70 that verifies:

- plugin directory exists
- registry exists
- Hermes PluginManager loads `capability-reuse` with `enabled=True` and `error=None`
- shadow mode hides `invoke_capability`
- active mode exposes `invoke_capability`
- prompt `check HMP health for peer128` retrieves `hmp-healthcheck`
- raw `execute_code` is blocked while an intervention is open
- `invoke_capability(hmp-healthcheck@1.0.0, peer128)` returns status ok
- false-positive prompts do not retrieve healthcheck:
  - `send a message to peer128 saying hello`
  - `deploy the HMP plugin to peer128`
- simulated clean timeout issues and consumes one fallback token
- event chain includes retrieval/intervention/state/invocation/outcome events

Known passing observed values from the session:

- retrieval score for `check HMP health for peer128`: `0.6916`
- live peer128 health latency: about `25–50 ms`
- PluginManager: `plugin_loaded=True enabled=True error=None`

## Pitfalls

- Do not conclude peer128 has the plugin merely because `/hmp/health` returns OK; that only proves HMP gateway is healthy.
- peer70 scheduler/cron deploy jobs may not execute promptly; if HMP reports the job was only scheduled, verify with a follow-up and be ready to run the generated script or direct sync path manually.
- Redact any API keys seen in peer70 deployment scripts; do not persist them in skills or memory.
