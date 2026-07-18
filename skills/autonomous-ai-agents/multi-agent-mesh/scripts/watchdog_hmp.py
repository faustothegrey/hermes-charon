#!/usr/bin/env python3
"""
Watchdog HMP — monitor system resources and report via HMP protocol.
Install on worker peers. Run every 30min via cron.
See references/hmp-watchdog-pattern.md for full documentation.
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

# Config
PEER_NAME = os.environ.get("HMP_PEER_NAME", "unknown")
COORDINATOR_URL = "http://192.168.178.70:8643"

# Critical thresholds
THRESHOLDS = {
    "disk_pct": 85,
    "ram_pct": 85,
    "load_avg_1": 4.0,
    "load_avg_5": 3.0,
    "uptime_days": 30,
    "temperature": 75,
}


def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def check_disk():
    out = run("df -h / | tail -1")
    parts = out.split()
    if len(parts) >= 5:
        pct = parts[4].rstrip("%")
        return int(pct), f"{parts[1]} total, {parts[2]} used, {parts[3]} avail ({parts[4]})"
    return 0, "unknown"


def check_ram():
    out = run("free -m | awk 'NR==2{print $2,$3,$4,$7}'")
    parts = out.split()
    if len(parts) >= 4:
        total, used, free, avail = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        pct = int(used / total * 100) if total > 0 else 0
        return pct, f"{used}MB/{total}MB used, {avail}MB available"
    return 0, "unknown"


def check_load():
    out = run("cat /proc/loadavg")
    parts = out.split()
    if len(parts) >= 3:
        l1, l5, l15 = float(parts[0]), float(parts[1]), float(parts[2])
        cpu = run("nproc")
        cores = int(cpu) if cpu else 1
        return l1, l5, l15, cores, f"{l1}/{l5}/{l15} (cores: {cores})"
    return 0, 0, 0, 1, "unknown"


def check_uptime():
    out = run("cat /proc/uptime")
    parts = out.split()
    if parts:
        sec = float(parts[0])
        days = int(sec // 86400)
        return days, f"{days} days"
    return 0, "unknown"


def check_temp():
    out = run("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
    if out:
        temp = int(out) / 1000
        return temp, f"{temp:.1f}°C"
    return 0, "N/A"


def send_alert(level, metric, value, detail):
    msg = {
        "hmp_version": "1.0",
        "message_id": f"watchdog_{PEER_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "idempotency_key": f"wd_{PEER_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "from": PEER_NAME,
        "to": "peer70",
        "type": "request",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": {
            "type": "watchdog_alert",
            "level": level,
            "metric": metric,
            "value": value,
            "detail": detail,
            "peer": PEER_NAME,
        },
    }
    data = json.dumps(msg).encode()
    try:
        req = urllib.request.Request(
            f"{COORDINATOR_URL}/hmp/send",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  [ERRORE] HMP send: {e}", file=sys.stderr)
        return None


def main():
    alerts = []

    disk_pct, disk_detail = check_disk()
    print(f"[DISCO] {disk_pct}% — {disk_detail}")
    if disk_pct > THRESHOLDS["disk_pct"]:
        alerts.append(("WARN", "disk_usage", f"{disk_pct}%", disk_detail))

    ram_pct, ram_detail = check_ram()
    print(f"[RAM]   {ram_pct}% — {ram_detail}")
    if ram_pct > THRESHOLDS["ram_pct"]:
        alerts.append(("WARN", "ram_usage", f"{ram_pct}%", ram_detail))

    l1, l5, l15, cores, load_detail = check_load()
    print(f"[LOAD]  {load_detail}")
    if l1 > THRESHOLDS["load_avg_1"]:
        alerts.append(("WARN", "load_1min", f"{l1}", load_detail))
    elif l5 > THRESHOLDS["load_avg_5"]:
        alerts.append(("INFO", "load_5min", f"{l5}", load_detail))

    days, uptime_detail = check_uptime()
    print(f"[UPTIME] {uptime_detail}")
    if days > THRESHOLDS["uptime_days"]:
        alerts.append(("INFO", "uptime", f"{days}d", f"Reboot recommended — uptime {uptime_detail}"))

    temp, temp_detail = check_temp()
    print(f"[TEMP]  {temp_detail}")
    if temp > THRESHOLDS["temperature"]:
        alerts.append(("WARN", "temperature", f"{temp:.1f}°C", temp_detail))

    if alerts:
        print(f"\n⚠ {len(alerts)} alert(s):")
        for level, metric, value, detail in alerts:
            print(f"  [{level}] {metric}: {value} — {detail}")
            send_alert(level, metric, value, detail)
    else:
        print("\n✅ All clear — no alerts")

    # Always send health report
    msg = {
        "hmp_version": "1.0",
        "message_id": f"health_{PEER_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "idempotency_key": f"hlth_{PEER_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "from": PEER_NAME,
        "to": "peer70",
        "type": "request",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": {
            "type": "health_report",
            "peer": PEER_NAME,
            "disk_usage_pct": disk_pct,
            "ram_usage_pct": ram_pct,
            "load_avg": {"1min": l1, "5min": l5, "15min": l15, "cores": cores},
            "uptime_days": days,
            "temperature": temp,
            "alert_count": len(alerts),
        },
    }
    data = json.dumps(msg).encode()
    try:
        req = urllib.request.Request(
            f"{COORDINATOR_URL}/hmp/send",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [ERRORE] Health report: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()