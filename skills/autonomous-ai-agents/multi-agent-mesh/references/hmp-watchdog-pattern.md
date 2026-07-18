# HMP-Based System Watchdog

Pattern for running a watchdog on worker peers that monitors system resources and reports via HMP protocol to the coordinator. Complements the API-based health monitoring (`/health` endpoint) by using HMP as the reporting channel.

## Architecture

```
Worker peer (cron every 30min)
  ├── Check: disk usage, RAM, load avg, uptime, temperature
  ├── If threshold exceeded → POST /hmp/send (watchdog_alert) → coordinator's HMP bus
  └── Always → POST /hmp/send (health_report) → coordinator's HMP bus
```

Two message types sent to coordinator (`to: "peer70"`):

| Type | When | Payload |
|------|------|---------|
| `watchdog_alert` | When a metric exceeds threshold | `{level, metric, value, detail, peer}` |
| `health_report` | Every run (always) | `{disk_usage_pct, ram_usage_pct, load_avg, uptime_days, temperature, alert_count}` |

## Watchdog Script

Location on the worker: `/usr/local/bin/watchdog_hmp.py`
Run via cron: `*/30 * * * * HMP_PEER_NAME=<peername> python3 /usr/local/bin/watchdog_hmp.py >/dev/null 2>&1`

### Configurable Thresholds (inside the script)

| Threshold | Default | Notes |
|-----------|---------|-------|
| `disk_pct` | 85% | Disk usage alert |
| `ram_pct` | 85% | RAM usage alert |
| `load_avg_1` | 4.0 | Load 1min > cores can indicate overload |
| `load_avg_5` | 3.0 | Sustained load alert (less urgent) |
| `uptime_days` | 30 | >30d suggests reboot for updates/health |
| `temperature` | 75°C | ARM thermal throttle threshold |

### Coordinator (peer70) Monitoring

The coordinator can read watchdog reports directly from the HMP SQLite DB:

```python
import sqlite3, json
conn = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db')
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT from_peer, payload, status, created_at FROM messages "
    "WHERE json_extract(payload, '$.type') IN ('watchdog_alert','health_report') "
    "ORDER BY created_at DESC LIMIT 20"
).fetchall()
for r in rows:
    p = json.loads(r['payload']) if r['payload'] else {}
    print(f"{r['created_at']} | {r['from_peer']} | {p.get('type','?')} | "
          f"alerts: {p.get('alert_count','?')} | status: {r['status']}")
conn.close()
```

### Cron Installation

On the worker peer (Fedora):

```bash
(crontab -l 2>/dev/null | grep -v watchdog_hmp; \
 echo '*/30 * * * * HMP_PEER_NAME=peerNN python3 /usr/local/bin/watchdog_hmp.py >/dev/null 2>&1') \
 | crontab -
```

### Full Script

The complete watchdog script is at `scripts/watchdog_hmp.py` in this skill. Key sections:

1. **`check_disk()`** — reads `df -h /`, returns usage percentage and detail string
2. **`check_ram()`** — reads `free -m`, returns percentage and detail
3. **`check_load()`** — reads `/proc/loadavg`, returns 1min/5min/15min + core count
4. **`check_uptime()`** — reads `/proc/uptime`, returns days
5. **`check_temp()`** — reads `/sys/class/thermal/thermal_zone0/temp`, returns °C
6. **`send_alert()`** — constructs HMP `watchdog_alert` message, POSTs to coordinator
7. **`main()`** — runs all checks, sends alerts + health_report

## Relation to API-based Health Monitoring

The existing `peer-health.py` pattern (API `/health` polling) and the HMP watchdog are **complementary**, not redundant:

| Aspect | API Health (`/health`) | HMP Watchdog (`/hmp/send`) |
|--------|----------------------|---------------------------|
| Direction | Coordinator polls peer | Peer pushes to coordinator |
| Latency | Real-time | Every 30min |
| Token cost | Zero | Zero |
| Auth | None on `/health` | None (LAN trust) |
| Data | Basic: status+version | Rich: disk, RAM, load, temp |
| Persistence | Volatile (JSON file) | SQLite (survives restart) |
| Use case | Alive/dead detection | Deep system health monitoring |

## Pitfalls

- **Peer must be registered in HMP mesh** — the watchdog assumes `hmp.py` is running on the worker and the coordinator's HMP server (`:8643`) is reachable
- **HMP_PEER_NAME env var** — the script reads `PEER_NAME` from `HMP_PEER_NAME` env var. The cron job MUST set it
- **Sqlite3 not on coordinator peer70** — use `python3 -c "import sqlite3..."` instead of the `sqlite3` CLI tool to query the DB
- **No feedback to worker** — the watchdog fires and forgets via HMP. If the coordinator is offline, the alert is silently dropped (URLError caught)
- **Fedora/dnf slowness** — on Fedora 30 ARM, `dnf install` can hang (network timeout, slow CPU). If you need to install `sshpass` for deployment, copy the binary via base64 pipe instead