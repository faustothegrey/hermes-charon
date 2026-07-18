# Backup Monitor — Script & Config Reference

## Script: `backup_monitor.py`

Located at `~/.hermes/scripts/backup_monitor.py`. Queries peer Hermes agents via their chat completions API about the status of a named backup cron job (identified by `job_id`). Designed to run every 30 min via Hermes cronjob.

### Flow

1. Read `peers_config.json` (same directory as script)
2. For each peer, POST to `http://{host}:{port}/v1/chat/completions`:
   - Model: `hermes-agent`
   - Prompt (Italian): "Stato del cron job backup {job_id}. Voglio solo: esito (success/error/running/never-ran), orario ultimo run, run totali. Rispondi SOLO con JSON valido, niente altro."
   - Expected JSON response format: `{"esito":"...","ultimo_run":"...","run_totali":N}`
3. Extract JSON from possible markdown code fences (```json ... ``` or ``` ... ```)
4. Write results to `~/.hermes/peer-network/backup_status.json`

### Output Format

```json
{
  "updated_at": 1776879831.0,
  "updated_at_str": "2026-07-11 05:30:31",
  "backups": [
    {
      "peer": "peer128",
      "label": "peer128 (Mac)",
      "reachable": true,
      "job_id": "b763d78565da",
      "esito": "success",
      "ultimo_run": "2026-07-11 04:00:00",
      "run_totali": 42,
      "timestamp": 1776879831.0
    }
  ]
}
```

`esito` values: `success`, `error`, `running`, `never-ran`, `offline`, `unknown`

## Config: `peers_config.json`

Located at `~/.hermes/scripts/peers_config.json`. Each peer entry:

```json
{
  "peer128": {
    "host": "192.168.178.112",
    "port": 8642,
    "api_key": "<hex key>",
    "job_id": "b763d78565da",
    "label": "peer128 (Mac)"
  }
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `host` | yes | — | Peer IP or hostname |
| `port` | no | 8642 | Hermes API server port |
| `api_key` | yes | — | Peer's API key (from its `~/.hermes/.env` or gateway config) |
| `job_id` | yes | — | The cron job ID on the peer to query (e.g. `b763d78565da`) |
| `label` | no | peer name | Human-readable label for display |

## Pitfalls

### Sequential Timeout Cascade

**The script's 30s per-peer timeout × 4 peers = 120s minimum execution time.** This exactly matches the cron pre-run script timeout (120s), meaning the script is **always at risk of being killed** during normal operation. If even one peer takes more than 30s, the remaining peers don't get queried.

**Mitigations (pick one):**

1. **Reduce per-peer timeout** — Change `timeout=30` to `timeout=15` or `timeout=10` in `urllib.request.urlopen(req, timeout=30)`. At 15s/peer, worst case = 60s. At 10s/peer, worst case = 40s.

2. **Use concurrent/async requests** — Query peers in parallel using `concurrent.futures.ThreadPoolExecutor` or `asyncio`. Total time becomes the slowest peer instead of the sum of all peers. Example:
   ```python
   from concurrent.futures import ThreadPoolExecutor, as_completed
   with ThreadPoolExecutor(max_workers=4) as pool:
       futures = {pool.submit(query_peer_backup, name, cfg): name for name, cfg in peers.items()}
       for future in as_completed(futures):
           results.append(future.result())
   ```

3. **Increase pre-run script timeout** — The cron pre-run script timeout is ~120s by default. This is set in the terminal config. Changing `terminal.timeout` in `config.yaml` to 240s gives the script more headroom, but doesn't solve the underlying sequential-latency problem.

4. **Move to `no_agent: true`** — If the backup monitor doesn't need LLM reasoning, convert the cron job to `no_agent: true` so the script runs as an independent subprocess with its own timeout, not limited by the agent session's inactivity timer.

### Missing `job_id` crashes

If a peer entry is missing `job_id`, the script crashes with `KeyError: 'job_id'` before reaching that peer. Always verify all fields are present.

### API key mismatch

The peer's API key must match what the peer's Hermes gateway expects. A wrong key returns `{"error": {"message": "Invalid API key"}}` from the API server.

### Peer offline

URLError/timeout is caught and recorded as `esito: "offline"`. The peer remains in the results list with `reachable: false`.

### Response parsing

The peer's Hermes agent must respond with valid JSON matching the expected format. If the agent returns non-JSON text or an unexpected structure, the catch-all exception handler records `esito: "error"`.

### Agent Session Cannot Re-Run the Script

When the pre-run script times out, the agent session starts but **cannot re-run the script** because:
- `terminal()` and `execute_code()` are blocked by the cron security scanner when `approvals.cron_mode` is not set
- Browser/web tools are cloud-based and can't reach LAN IPs
- The agent only sees the pre-run script's partial stdout (which may be empty)

**Fallback:** When the pre-run script output is empty or partial, the cron agent should:
1. Check the last backup_status.json via `read_file` to see previous state
2. Read `status.json` from `~/.hermes/peer-network/` for peer reachability data
3. Compile a combined status report from these fallback sources
4. Write the updated report to `backup_status.json`
5. Note the data is stale (pre-run script timed out) in the output