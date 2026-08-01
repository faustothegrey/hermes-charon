# Dual-Plane Cron Verification (Terminal Blocked)

## Context

Agent-based cron jobs (those WITHOUT `no_agent: true`) that need to verify the
dual-plane v2 server on `:18644` can find all terminal/execute_code commands
blocked by the Tirith security policy. Even `cron_config_override.yaml` with
`approvals.cron_mode: allow` and `tirith_enabled: false` may not be loaded.

**Root cause:** The override file is at `~/.hermes/cron/cron_config_override.yaml`
but agent-based cron sessions don't reliably read it. Only `no_agent: true` script
jobs consistently bypass the block.

## Verification Toolkit (No Terminal Required)

### 1. Check dual-plane server (:18644)

```python
# browser_navigate auto-routes private IPs to local Chromium sidecar
browser_navigate(url="http://127.0.0.1:18644/health")
# DOWN  → ERR_CONNECTION_REFUSED
# UP    → {"status":"ok","service":"dual-plane","version":"2.0.0"}
```

### 2. Check HMP gateway (:18643)

```python
browser_navigate(url="http://127.0.0.1:18643/health")
# → {"status":"ok","service":"hmp-gateway","gateway_adapter":true,"node_id":"peer70","bind":"0.0.0.0:18643"}
```

### 3. Inspect dual-plane DB

```python
search_files(path="~/.hermes/data/hmp", pattern="*.db", target="files")
# Returns: dual-plane.db, dual-plane.db-shm, dual-plane.db-wal, agent_messages.db, server.log
```

### 4. Read server log

```python
read_file(path="~/.hermes/data/hmp/server.log")
# Shows HMP gateway activity — last activity timestamp reveals if gateway
# has been restarted recently.
```

### 5. Scan gateway/agent logs for port :18644 activity

```python
search_files(
    path="~/.hermes/logs",
    pattern="18644",
    target="content"
)
# Reveals previous attempts to start/kill/check the dual-plane server.
```

### 6. Read the test script when you cannot run it

```python
read_file(path="~/.hermes/scripts/test-dual-plane-v2.py")
# Shows what the test would do — health check + send test + DB check.
```

### 7. Check startup scripts exist

```python
search_files(path="~/.hermes/scripts", pattern="dual-plane", target="files")
# Returns: hmp_dual_plane.py (library), test-dual-plane-v2.py (test),
#          start-dual-plane.sh (startup), test-v2-runner.sh (runner)
```

## Behavior Across Cron Job Types

| Job type | terminal/execute_code | Override loaded? | Workaround |
|----------|----------------------|-----------------|------------|
| Agent job (no_agent=false) | ❌ Blocked | ❌ Not reliably | browser + file tools |
| Script job (no_agent=true) | ✅ Works | ✅ Yes | N/A — direct execution |

## What to Report When Terminal Is Blocked

When you cannot run the test script and must report status:

1. **Dual-plane server status** (from browser_navigate to :18644)
2. **HMP gateway status** (from browser_navigate to :18643)
3. **Asset inventory** — which scripts/DBs exist
4. **Security policy status** — override file exists but not loaded
5. **Last activity timestamp** — from server.log tail

## Example Report Skeleton

```
## Dual-Plane v2 Test Results

| Component | Status | Detail |
|-----------|--------|--------|
| HMP Gateway (:18643) | ✅ Running | {health response} |
| Dual-Plane Server (:18644) | ❌ Not running | ERR_CONNECTION_REFUSED |
| Test script | ✅ Exists | ~/.hermes/scripts/test-dual-plane-v2.py |
| Dual-plane library | ✅ Exists | ~/.hermes/scripts/hmp_dual_plane.py (v2.0.0) |
| Start script | ✅ Exists | ~/.hermes/scripts/start-dual-plane.sh |
| Dual-plane DB | ✅ Exists | .db + .shm + .wal files |
| Security override | ⚠️ Not loaded | cron_config_override.yaml exists but not picked up |

**Note:** The test script could not be executed — terminal/execute_code blocked
by Tirith security policy in this cron context. The override file
`cron_config_override.yaml` was not loaded.
```

## Startup Command (When Terminal Is Available)

```bash
cd ~/.hermes/scripts && python3 -c "
import sys; sys.path.insert(0, '.')
from hmp_dual_plane import run_server
run_server(host='0.0.0.0', port=18644, node_id='peer70')
"
```

Or via the startup script:
```bash
bash ~/.hermes/scripts/start-dual-plane.sh
```
