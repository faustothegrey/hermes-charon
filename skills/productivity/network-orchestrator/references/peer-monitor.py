#!/usr/bin/env python3
"""
peer-monitor.py — Orchestratore rete peer
Pinga tutti i peer conosciuti e scopre nuovi dispositivi LAN.
Eseguito ogni ora da cronjob Hermes.

To adapt for your network:
1. Edit KNOWN_PEERS and IGNORE_IPS at the top
2. Change the wifi interface in run_cmd(["ip", "neigh", "show", "dev", "wlan0"]) if needed
3. Run manually to test: python3 peer-monitor.py
4. Register in cron: cronjob(action='create', schedule='every 1h', script='peer-monitor.py', ...)
"""
import subprocess
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STATUS_FILE = HOME / ".hermes/peer-network/STATUS.md"
STATUS_JSON = HOME / ".hermes/peer-network/status.json"
HISTORY_LOG = HOME / ".hermes/peer-network/history.log"
STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ========== CONFIGURATION — EDIT THESE ==========
# (name, host, description)
KNOWN_PEERS = [
    ("peer70",  "127.0.0.1",                         "questo Raspberry Pi (Debian 11 aarch64)"),
    ("peer84",  "192.168.178.84",                    "N56VV laptop (Ubuntu 22.04)"),
    ("peer60",  "192.168.178.60",                    "Raspberry Pi 3 (Raspbian 9)"),
    ("peer-host", "Faustos-MacBook-Pro-Home-3.fritz.box", "Mac (macOS 26.5.1 / vecchio orchestratore)"),
]

IGNORE_IPS = {
    "192.168.178.1",   # router
    "192.168.178.84",  # peer84
    "192.168.178.60",  # peer60
}

WIFI_IFACE = "wlan0"  # change to your interface (eth0, enp1s0, etc.)
# ==================================================

def run_cmd(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except FileNotFoundError:
        return "", -2

def ping_peer(host):
    """Returns (status, rtt_ms)"""
    out, rc = run_cmd(["ping", "-c", "1", "-W", "3", host])
    if rc == 0:
        m = re.search(r'=\s*([0-9.]+)/', out) or re.search(r'time=([0-9.]+)\s*ms', out)
        rtt = m.group(1) if m else "0"
        return "ONLINE", rtt
    return "OFFLINE", "0"

def discover_arp():
    """Find new devices on LAN via ip neigh"""
    out, rc = run_cmd(["ip", "neigh", "show", "dev", WIFI_IFACE])
    if rc != 0:
        return []
    devices = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ip = parts[0]
        # Skip IPv6
        if ip.startswith("fe80") or ip.startswith("fd00"):
            continue
        if ip in IGNORE_IPS:
            continue
        state = parts[-1]
        mac = parts[3]
        if mac == "<incomplete>":
            continue
        if state == "FAILED":
            continue
        # Skip known peers
        if any(ip == p[1] for p in KNOWN_PEERS):
            continue
        # Resolve hostname
        hostname = ip
        out2, _ = run_cmd(["host", ip])
        m = re.search(r'name pointer\s+(\S+)', out2)
        if m:
            hostname = m.group(1).rstrip('.')
        devices.append((ip, mac, hostname, state))
    return devices

def get_system_metrics():
    temp_out, _ = run_cmd(["cat", "/sys/class/thermal/thermal_zone0/temp"])
    temp_c = int(temp_out.strip()) // 1000 if temp_out else 0
    load_out, _ = run_cmd(["cat", "/proc/loadavg"])
    load = load_out.split()[:3] if load_out else ["?", "?", "?"]
    mem_out, _ = run_cmd(["free", "-h"])
    mem_used, mem_total = "?", "?"
    for line in mem_out.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            mem_used, mem_total = parts[2], parts[1]
            break
    uptime_out, _ = run_cmd(["uptime", "-p"])
    uptime = uptime_out.replace("up ", "") if uptime_out else "?"
    return {
        "temp_c": temp_c,
        "load_1m": load[0] if len(load) > 0 else "?",
        "load_5m": load[1] if len(load) > 1 else "?",
        "load_15m": load[2] if len(load) > 2 else "?",
        "mem_used": mem_used,
        "mem_total": mem_total,
        "uptime": uptime,
    }

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    epoch = int(datetime.now().timestamp())

    # === PING KNOWN PEERS ===
    results = {}
    lines = []
    lines.append(f"🌐 **Peer Monitor** — {now}")
    lines.append("")
    lines.append("## Stato Peer")
    lines.append("| Peer | IP | Macchina | Stato | RTT |")
    lines.append("|---|---|---|---|---|")
    
    for name, host, desc in KNOWN_PEERS:
        if name == "peer70":
            results[name] = "ONLINE"
            lines.append(f"| **{name}** 🏆 | {host} | {desc} | 🟢 ONLINE (self) | — |")
            continue
        
        status, rtt = ping_peer(host)
        results[name] = status
        icon = "🟢" if status == "ONLINE" else "🔴"
        lines.append(f"| {name} | `{host}` | {desc} | {icon} {status} | {rtt}ms |")
    
    # === DISCOVER NEW DEVICES ===
    lines.append("")
    lines.append("## Nuovi Dispositivi Rilevati")
    new_devices = discover_arp()
    if new_devices:
        lines.append("| IP | MAC | Hostname | Stato ARP |")
        lines.append("|---|---|---|---|")
        for ip, mac, hostname, state in new_devices:
            lines.append(f"| `{ip}` | {mac} | {hostname} | {state} |")
    else:
        lines.append("Nessun nuovo dispositivo rilevato.")
    
    # === SYSTEM METRICS ===
    sys_metrics = get_system_metrics()
    lines.append("")
    lines.append("## Metriche Sistema (orchestratore)")
    lines.append(f"- 🌡️ Temperatura CPU: **{sys_metrics['temp_c']}°C**")
    lines.append(f"- 📊 Load avg: {sys_metrics['load_1m']}, {sys_metrics['load_5m']}, {sys_metrics['load_15m']}")
    lines.append(f"- 💾 RAM: {sys_metrics['mem_used']} / {sys_metrics['mem_total']}")
    lines.append(f"- ⏱️ Uptime: {sys_metrics['uptime']}")
    
    output = "\n".join(lines)
    
    # === SAVE STATUS FILE (markdown) ===
    md_lines = [
        "# 🌐 Peer Network — Stato Orchestrato",
        "",
        f"_Ultimo aggiornamento: {now}_",
        "",
        "## Stato Peer",
        "",
        "| Peer | IP | Macchina | Stato |",
        "|---|---|---|---|",
    ]
    for name, host, desc in KNOWN_PEERS:
        s = results.get(name, "OFFLINE")
        if name == "peer70":
            md_lines.append(f"| **{name}** 🏆 | {host} | {desc} | 🟢 ONLINE (orchestratore) |")
        else:
            ico = "🟢" if s == "ONLINE" else "🔴"
            md_lines.append(f"| {name} | `{host}` | {desc} | {ico} {s} |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("## Cronologia")
    md_lines.append("")
    md_lines.append(f"- {now} — Monitoraggio completato")
    
    STATUS_FILE.write_text("\n".join(md_lines) + "\n")
    
    # === SAVE JSON ===
    json_data = {
        "timestamp": now,
        "epoch": epoch,
        "orchestrator": f"{KNOWN_PEERS[0][1]} ({KNOWN_PEERS[0][2]})",
        "peers": {},
        "system": {
            "temp_c": sys_metrics["temp_c"],
            "load": f"{sys_metrics['load_1m']}, {sys_metrics['load_5m']}, {sys_metrics['load_15m']}",
            "memory": f"{sys_metrics['mem_used']} / {sys_metrics['mem_total']}",
        }
    }
    for name, host, desc in KNOWN_PEERS:
        s = results.get(name, "OFFLINE")
        rtt = ""
        if name != "peer70":
            _, rtt = ping_peer(host)
        json_data["peers"][name] = {
            "ip": host,
            "note": desc,
            "status": s,
            "rtt_ms": rtt or 0,
        }
    STATUS_JSON.write_text(json.dumps(json_data, indent=2) + "\n")
    
    # === HISTORY LOG ===
    log_line = f"{epoch}|{now}|"
    for name, host, desc in KNOWN_PEERS:
        if name == "peer70":
            continue
        log_line += f"{name}={results.get(name, '?')} "
    with open(HISTORY_LOG, "a") as f:
        f.write(log_line.strip() + "\n")
    
    # === DETECT CHANGES ===
    if HISTORY_LOG.exists():
        logs = HISTORY_LOG.read_text().strip().splitlines()
        if len(logs) >= 2:
            prev_line = logs[-2]
            curr_line = logs[-1]
            prev_part = prev_line.split("|")[-1].strip()
            curr_part = curr_line.split("|")[-1].strip()
            if prev_part != curr_part:
                output += "\n\n⚠️ **Cambiamento di stato rilevato!**"
                prev_dict = {}
                for item in prev_part.split():
                    if "=" in item:
                        k, v = item.split("=", 1)
                        prev_dict[k] = v
                for item in curr_part.split():
                    if "=" in item:
                        k, v = item.split("=", 1)
                        if prev_dict.get(k) != v:
                            arrow = "🟢 ONLINE" if v == "ONLINE" else "🔴 OFFLINE"
                            output += f"\n- {k}: ora **{arrow}**"
    
    print(output)
    return 0

if __name__ == "__main__":
    sys.exit(main())
