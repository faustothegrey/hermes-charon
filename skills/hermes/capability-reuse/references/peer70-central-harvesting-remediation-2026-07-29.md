# peer70 central harvesting remediation — 2026-07-29

## Trigger

Fausto asked peer70 to update its own `capability-reuse` skill/plugin and enable passive data collection, then asked for a single place to collect and analyze recorded data from all agents.

## Durable lessons

- For capability-reuse harvesting, treat HMP as the control plane only. Do not move raw JSONL or base64 archives through HMP messages; message size limits and agent context make that brittle.
- Use a data plane for files: local filesystem, SSH/scp/rsync where credentials exist, or a future read-only export endpoint.
- A peer claiming scripts are prepared is not sufficient. Verify:
  - skill version
  - runtime plugin version
  - `plugins.enabled` includes both `hmp` and `capability-reuse`
  - gateway restarted/healthy
  - a fresh post-probe `retrieval_event`
  - analyzer output in the standard path
  - central collector report includes the peer
- If HMP-DM execution cannot run terminal/execute_code because approvals are not visible, use direct maintenance/data-plane access only after the user has explicitly asked to fix the blocker. Prefer peer autonomy first.
- Avoid Hermes one-shot cron as the only remediation path on peer70 when immediate execution is required. In this session, peer70 reported one-shot/repeat-once cron jobs did not run; the durable solution was system crontab recurring jobs plus immediate verification.

## Final peer70 state after remediation

- `capability-reuse` skill and runtime plugin synced to v2.3.0.
- `plugins.enabled` set to `[hmp, capability-reuse]`.
- Gateway restarted and HMP probe returned `OK`.
- Passive shadow harvesting fresh: 1116 events, latest retrieval `2026-07-29T14:13:36Z`.
- Standard analyzer installed at `~/.hermes/scripts/batch-reuse-analyzer.py` and scheduled every 15 minutes.
- Analyzer writes `~/.hermes/data/reuse-aggregati/latest.json` and `runs/*.json`.
- Central collector installed at `~/.hermes/scripts/central-collector.py` and scheduled every 30 minutes.
- Collector writes:
  - raw files: `~/.hermes/data/capreuse-central/raw/<peer>/events.jsonl`
  - aggregates: `~/.hermes/data/capreuse-central/aggregates/<peer>/latest.json`
  - reports: `~/.hermes/data/capreuse-central/reports/latest.json`

## Initial central pull status

- peer70: OK, raw events and aggregate copied centrally.
- peer106: OK, raw events and aggregate copied centrally.
- peer84: missing harvesting files.
- peer128: SSH pull unreachable from peer70.
- peer138: data plane unconfigured.
- peer58: data plane unconfigured.

## Review package email

Fausto asked to email the complete skill zip for review. The usable email path was peer70's Himalaya configuration.

- Recipient: `fausto.lelli@gmail.com`
- Sender: `fausto.lelli@virgilio.it`
- Sent using `himalaya template send` with MML attachment from peer70.
- Zip path on peer70: `/tmp/capability-reuse-skill-v2.3.0-20260729T141922Z.zip`
- SHA256: `37c9c8a4ffbe23dd1af383671394c9367bed34ffe9d9c846ac739ce78c18fde2`
- Size: 326539 bytes

## Status caveat

This remediation improves passive data acquisition and review packaging only. Formal status remains unchanged: passive shadow GO; formal Phase 0 empirical closure and formal active rollout remain NO-GO until human labels, actual retriever evaluation, threshold calibration, and pinned-runtime evidence are complete.
