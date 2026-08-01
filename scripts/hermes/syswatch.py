#!/usr/bin/env python3
"""
syswatch — Lightweight system watchdog
CPU, memory (incl. swap), and I/O monitoring.
Runs every N minutes via cron.
Logs to JSONL. Alerts via HMP if thresholds exceeded.
Impatto trascurabile: solo /proc reads, nessun subprocess pesante.
"""
import json, os, time, sys
from pathlib import Path
from datetime import datetime, timezone

HERMES_HOME = Path.home() / ".hermes"
LOG_DIR = HERMES_HOME / "data" / "syswatch"
LOG_FILE = LOG_DIR / "metrics.jsonl"
ALERT_LOG = LOG_DIR / "alerts.json"

# ── Thresholds (configurabili) ──
THRESHOLDS = {
    "cpu_load_1m":  (float(os.environ.get("SW_CPU_1M",  "4.0")),  "CPU load 1m > {val}"),
    "cpu_load_5m":  (float(os.environ.get("SW_CPU_5M",  "3.0")),  "CPU load 5m > {val}"),
    "mem_pct":      (float(os.environ.get("SW_MEM_PCT", "85.0")), "Memory usage > {val}%"),
    "swap_pct":     (float(os.environ.get("SW_SWAP_PCT","50.0")), "Swap usage > {val}%"),
    "swap_used_mb": (float(os.environ.get("SW_SWAP_MB", "512.0")),"Swap used > {val} MB"),
}

def read_proc(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default

def parse_meminfo():
    """Parse /proc/meminfo into a dict."""
    raw = read_proc("/proc/meminfo")
    if not raw:
        return {}
    mem = {}
    for line in raw.split("\n"):
        parts = line.split(":")
        if len(parts) == 2:
            key = parts[0].strip()
            val_str = parts[1].strip().split()[0] if parts[1].strip() else "0"
            try:
                mem[key] = int(val_str)  # kB
            except ValueError:
                mem[key] = 0
    return mem

def parse_loadavg():
    """Parse /proc/loadavg."""
    raw = read_proc("/proc/loadavg")
    if not raw:
        return (0.0, 0.0, 0.0)
    parts = raw.split()
    return (float(parts[0]), float(parts[1]), float(parts[2]))

def parse_stat():
    """Return CPU times from /proc/stat (user, nice, system, idle, iowait)."""
    raw = read_proc("/proc/stat")
    if not raw:
        return None
    for line in raw.split("\n"):
        if line.startswith("cpu "):
            fields = line.split()
            return {
                "user": int(fields[1]),
                "nice": int(fields[2]),
                "system": int(fields[3]),
                "idle": int(fields[4]),
                "iowait": int(fields[5]),
            }
    return None

def parse_diskstats():
    """Read basic disk I/O from /proc/diskstats (sda only, for simplicity)."""
    raw = read_proc("/proc/diskstats")
    if not raw:
        return None
    for line in raw.split("\n"):
        parts = line.split()
        if len(parts) >= 14 and parts[2] in ("sda", "mmcblk0", "nvme0n1"):
            return {
                "device": parts[2],
                "reads_completed": int(parts[3]),
                "sectors_read": int(parts[5]),
                "writes_completed": int(parts[7]),
                "sectors_written": int(parts[9]),
                "io_in_progress": int(parts[11]),
            }
    return None

def collect():
    """Collect all metrics in one pass."""
    mem = parse_meminfo()
    load = parse_loadavg()
    stat = parse_stat()
    disk = parse_diskstats()

    total_kb = mem.get("MemTotal", 1)
    free_kb = mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0)
    used_kb = total_kb - free_kb
    mem_pct = (used_kb / total_kb) * 100 if total_kb else 0

    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = swap_total - swap_free
    swap_pct = (swap_used / swap_total) * 100 if swap_total else 0

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hostname": os.uname().nodename,
        "cpu": {
            "load_1m":  round(load[0], 2),
            "load_5m":  round(load[1], 2),
            "load_15m": round(load[2], 2),
        },
        "memory": {
            "total_kb": total_kb,
            "used_kb": used_kb,
            "free_kb": free_kb,
            "used_pct": round(mem_pct, 1),
        },
        "swap": {
            "total_kb": swap_total,
            "used_kb": swap_used,
            "free_kb": swap_free,
            "used_pct": round(swap_pct, 1),
        },
        "io": {
            "device": disk["device"] if disk else "?",
            "reads": disk["reads_completed"] if disk else 0,
            "writes": disk["writes_completed"] if disk else 0,
            "io_in_progress": disk["io_in_progress"] if disk else 0,
        } if disk else None,
    }

def check_thresholds(metrics):
    """Return list of active alerts."""
    alerts = []
    load = metrics["cpu"]
    mem = metrics["memory"]
    swap = metrics["swap"]

    checks = [
        ("cpu_load_1m", load["load_1m"]),
        ("cpu_load_5m", load["load_5m"]),
        ("mem_pct",     mem["used_pct"]),
        ("swap_pct",    swap["used_pct"]),
        ("swap_used_mb", swap["used_kb"] / 1024),
    ]

    for key, val in checks:
        threshold, msg_template = THRESHOLDS.get(key, (float("inf"), ""))
        if val > threshold:
            alerts.append({
                "metric": key,
                "value": val,
                "threshold": threshold,
                "message": msg_template.replace("{val}", f"{threshold}").replace("{v}", f"{val:.1f}"),
            })
    return alerts

def log_metrics(metrics):
    """Append to JSONL log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(metrics) + "\n")

def log_alert(alert):
    """Append alert to alerts log (keep last 100)."""
    try:
        if ALERT_LOG.exists():
            with open(ALERT_LOG) as f:
                alerts = json.load(f)
        else:
            alerts = []
    except (json.JSONDecodeError, OSError):
        alerts = []
    alerts.append(alert)
    # Keep last 100
    if len(alerts) > 100:
        alerts = alerts[-100:]
    with open(ALERT_LOG, "w") as f:
        json.dump(alerts, f, indent=2)

def get_stats():
    """Read log file for quick stats."""
    if not LOG_FILE.exists():
        return {"samples": 0}
    try:
        with open(LOG_FILE) as f:
            lines = [l for l in f if l.strip()]
        return {
            "samples": len(lines),
            "file": str(LOG_FILE),
        }
    except OSError:
        return {"samples": 0}

def main():
    metrics = collect()
    log_metrics(metrics)

    # Check thresholds and alert
    alerts = check_thresholds(metrics)
    for a in alerts:
        a["timestamp"] = metrics["timestamp"]
        log_alert(a)
        print(f"⚠️ ALERT: {a['message']} (value={a['value']:.1f}, threshold={a['threshold']})")

    # Always print summary (cron captures stdout)
    mem = metrics["memory"]
    swap = metrics["swap"]
    cpu = metrics["cpu"]
    io = metrics["io"]

    print(f"[syswatch] CPU:{cpu['load_1m']}/{cpu['load_5m']}/{cpu['load_15m']}  "
          f"MEM:{mem['used_pct']}%({mem['used_kb']//1024}MB)  "
          f"SWAP:{swap['used_pct']}%({swap['used_kb']//1024}MB)  "
          f"IO:{io['io_in_progress'] if io else '?'}  "
          f"Alerts:{len(alerts)}")

if __name__ == "__main__":
    main()