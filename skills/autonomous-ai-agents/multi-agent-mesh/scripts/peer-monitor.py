#!/usr/bin/env python3
"""peer-health.py — Coordinated health check of all Hermes peers via /health API.
Called by the orchestrator to monitor peer fleet status.
Communicates exclusively via Hermes API on :8642 — no SSH.
"""
import json, urllib.request, urllib.error, sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STATUS_FILE = HOME / ".hermes/peer-network/status.json"
HISTORY_FILE = HOME / ".hermes/peer-network/history.log"
STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Define the peer fleet: name → (host, port, role, description)
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
        body = json.loads(resp.read().decode())
        if body.get("status") == "ok":
            return "ONLINE", body.get("version", body.get("platform", "?"))
        return "DEGRADED", body[:60]
    except json.JSONDecodeError:
        return "DEGRADED", "bad-json"
    except urllib.error.HTTPError as e:
        return "ONLINE" if e.code in (401, 403) else "DEGRADED", f"http-{e.code}"
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

    for name, info in PEERS.items():
        status, version = check_health(name, info["host"], info["port"])
        results[name] = status
        version_info[name] = version

    # Build status JSON
    data = {
        "timestamp": timestamp,
        "epoch": epoch,
        "orchestrator": "peer70 (coordinator)",
        "peers": {},
        "transitions": [],
    }
    for name, info in PEERS.items():
        data["peers"][name] = {
            "ip": info["host"], "port": info["port"],
            "role": info["role"], "note": info["desc"],
            "status": results[name], "version": version_info[name],
        }

    # Append to history log
    log_entry = f"{epoch}|{timestamp}|{' '.join(f'{k}={results[k]}' for k in PEERS if k != 'peer70')}"
    with open(HISTORY_FILE, "a") as f:
        f.write(log_entry + "\n")

    # Detect transitions from last run
    if HISTORY_FILE.exists():
        lines = HISTORY_FILE.read_text().strip().splitlines()
        if len(lines) >= 2:
            prev = lines[-2].split("|")[-1].strip()
            curr = lines[-1].split("|")[-1].strip()
            if prev and curr and prev != curr:
                prev_d = dict(item.split("=") for item in prev.split() if "=" in item)
                for item in curr.split():
                    if "=" in item:
                        k, v = item.split("=", 1)
                        if prev_d.get(k) != v:
                            data["transitions"].append({
                                "peer": k, "from": prev_d.get(k, "?"),
                                "to": v, "timestamp": timestamp,
                            })

    STATUS_FILE.write_text(json.dumps(data, indent=2) + "\n")

    # Print summary
    print(f"Peer Network Health — {timestamp}")
    print("═" * 40)
    for name in sorted(PEERS):
        s = results[name]
        icon = {"ONLINE": "🟢", "OFFLINE": "🔴", "DEGRADED": "🟡"}.get(s, "⚪")
        print(f"  {icon} {name:10s}  {s:8s}  {version_info[name] or '?'}")
    if data["transitions"]:
        print("\n⚠  Transitions:")
        for t in data["transitions"]:
            print(f"  {t['peer']}: {t['from']} → {t['to']}")

if __name__ == "__main__":
    sys.exit(main())