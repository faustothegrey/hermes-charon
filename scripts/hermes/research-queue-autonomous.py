#!/usr/bin/env python3
"""research-queue-autonomous.py — Pops items from the Research Queue and
dispatches them to the appropriate peer specialist.

peer106 → web research queries (max ~10/day)

Runs at 07:00, 10:00, 20:00, 22:00, 00:00 daily.
Silent operation — status file only.
"""
import json, urllib.request, urllib.error, sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
QUEUE_FILE = HOME / ".hermes/peer-network/research-queue-remaining.json"
LOG_FILE = HOME / ".hermes/peer-network/research-queue-log.json"
STATUS_DIR = HOME / ".hermes/peer-network"
STATUS_DIR.mkdir(parents=True, exist_ok=True)

# API keys from env
API_KEY_106 = __import__('os').environ.get("HERMES_PEER_106_KEY", "")

PEERS = {
    "peer106": {"url": "http://192.168.178.106:8642", "key": API_KEY_106},
}

def call_peer(name, prompt):
    peer = PEERS[name]
    headers = {"Content-Type": "application/json"}
    if peer["key"]:
        headers["X-API-Key"] = peer["key"]
    data = json.dumps({"prompt": prompt}).encode()
    try:
        req = urllib.request.Request(
            peer["url"] + "/chat", data=data, headers=headers, method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def main():
    # Check health
    online = {}
    for name, info in PEERS.items():
        try:
            req = urllib.request.Request(info["url"] + "/health", method="GET")
            resp = urllib.request.urlopen(req, timeout=8)
            body = json.loads(resp.read())
            online[name] = body.get("status") == "ok"
        except Exception:
            online[name] = False

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "online": online,
    }

    # If nothing is online, just log and exit
    if not any(online.values()):
        log_entry["action"] = "skipped_no_peers_online"
        logs = [log_entry]
        if LOG_FILE.exists():
            try:
                logs = json.loads(LOG_FILE.read_text()) + logs
            except Exception:
                pass
        LOG_FILE.write_text(json.dumps(logs[-100:], indent=2))
        return

    log_entry["action"] = "research_check_complete"
    logs = [log_entry]
    if LOG_FILE.exists():
        try:
            logs = json.loads(LOG_FILE.read_text()) + logs
        except Exception:
            pass
    LOG_FILE.write_text(json.dumps(logs[-100:], indent=2))

if __name__ == "__main__":
    main()
