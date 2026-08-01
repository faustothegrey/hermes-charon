#!/usr/bin/env python3
"""peer106-heartbeat.py — Health check for peer106 (web research specialist).
Runs hourly via cron. Silent — only writes status, no delivery unless transition.
"""
import json, urllib.request, urllib.error, sys
from datetime import datetime
from pathlib import Path

PEER_URL = "http://192.168.178.106:8642/health"
STATUS_DIR = Path.home() / ".hermes/peer-network"
STATUS_FILE = STATUS_DIR / "peer106-status.json"
STATUS_DIR.mkdir(parents=True, exist_ok=True)

def check():
    try:
        req = urllib.request.Request(PEER_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=8)
        body = json.loads(resp.read().decode())
        status = body.get("status", "UNKNOWN")
        version = body.get("version", body.get("platform", "?"))
        return "ONLINE", version
    except Exception:
        return "OFFLINE", str(sys.exc_info()[1])[:80]

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status, version = check()

    prev = {"status": "UNKNOWN"}
    if STATUS_FILE.exists():
        try:
            prev = json.loads(STATUS_FILE.read_text())
        except Exception:
            pass

    data = {
        "timestamp": now,
        "peer": "peer106",
        "status": status,
        "version": version,
    }
    STATUS_FILE.write_text(json.dumps(data, indent=2) + "\n")

    if prev.get("status") != status:
        print(f"[peer106] TRANSITION: {prev.get('status', '?')} -> {status}")

main()