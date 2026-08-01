#!/usr/bin/env python3
"""peer-health.py — Coordinated health check of all Hermes peers via /health API.
Called by peer70 (coordinator) to monitor peer fleet status.
Communicates exclusively via Hermes API on :8642 — no SSH.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STATUS_FILE = HOME / ".hermes/peer-network/status.json"
HISTORY_FILE = HOME / ".hermes/peer-network/history.log"
STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

PEERS = {
    "peer70":  {"host": "127.0.0.1",        "port": 8642, "role": "coordinator", "desc": "RPi4 orchestratore 24/7"},
    "peer84":  {"host": "192.168.178.84",    "port": 8642, "role": "worker",      "desc": "N56VV heavy lifting"},
    "peer105": {"host": "192.168.178.105",   "port": 8642, "role": "worker",      "desc": "RPi3B YouTube transcript"},
    "peer106": {"host": "192.168.178.106",   "port": 8642, "role": "worker",      "desc": "ARMv8 web research"},
    "peer128": {"host": "192.168.178.128",   "port": 8642, "role": "worker",      "desc": "MacBook Pro (offline)"},
}


def check_health(name, host, port):
    """Returns (status, version_or_error) using /health endpoint."""
    if name == "peer70":
        return "ONLINE", "self"
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        body = resp.read().decode()
        data = json.loads(body)
        status = data.get("status", "unknown")
        if status == "ok":
            version = data.get("version", data.get("platform", "?"))
            return "ONLINE", version
        return "DEGRADED", body[:60]
    except json.JSONDecodeError:
        return "DEGRADED", "bad-json"
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            return "ONLINE", f"auth ({e.code})"
        return "DEGRADED", f"http-{e.code}"
    except urllib.error.URLError as e:
        return "OFFLINE", str(e.reason)
    except Exception as e:
        return "OFFLINE", str(e)


def main():
    now = datetime.now()
    epoch = int(now.timestamp())
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    results = {}
    version_info = {}
    transitions = []

    # Check all peers
    for name, info in PEERS.items():
        status, version = check_health(name, info["host"], info["port"])
        results[name] = status
        version_info[name] = version

    # Build status file
    data = {
        "timestamp": timestamp,
        "epoch": epoch,
        "orchestrator": "peer70 (192.168.178.70 — coordinator)",
        "peers": {},
    }
    for name, info in PEERS.items():
        data["peers"][name] = {
            "ip": info["host"],
            "port": info["port"],
            "role": info["role"],
            "note": info["desc"],
            "status": results[name],
            "version": version_info[name],
        }

    # History log
    log_line = f"{epoch}|{timestamp}|"
    for name in PEERS:
        if name != "peer70":
            log_line += f"{name}={results[name]} "
    with open(HISTORY_FILE, "a") as f:
        f.write(log_line.strip() + "\n")

    # Detect transitions from last run
    if HISTORY_FILE.exists():
        lines = HISTORY_FILE.read_text().strip().splitlines()
        if len(lines) >= 2:
            prev = lines[-2].split("|")[-1].strip() if len(lines) >= 2 else ""
            curr = lines[-1].split("|")[-1].strip()
            if prev and curr and prev != curr:
                prev_dict = {}
                for item in prev.split():
                    if "=" in item:
                        k, v = item.split("=", 1)
                        prev_dict[k] = v
                for item in curr.split():
                    if "=" in item:
                        k, v = item.split("=", 1)
                        if prev_dict.get(k) != v:
                            transitions.append({
                                "peer": k,
                                "from": prev_dict.get(k, "?"),
                                "to": v,
                                "timestamp": timestamp,
                                "epoch": epoch,
                            })

    data["transitions"] = transitions
    STATUS_FILE.write_text(json.dumps(data, indent=2) + "\n")

    # Print summary for delivery
    print(f"Peer Network Health — {timestamp}")
    print("═" * 40)
    for name in sorted(PEERS):
        s = results[name]
        icon = {"ONLINE": "🟢", "OFFLINE": "🔴", "DEGRADED": "🟡"}.get(s, "⚪")
        v = version_info[name] or "?"
        print(f"  {icon} {name:10s}  {s:8s}  {v}")
    if transitions:
        print()
        print("⚠ Transitions detected:")
        for t in transitions:
            print(f"  {t['peer']}: {t['from']} → {t['to']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())