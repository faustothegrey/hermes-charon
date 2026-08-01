#!/usr/bin/env python3
"""Run backup_monitor.py piping current status data through stdin."""
import json
import subprocess
import sys
import os
import time
import datetime

status_path = os.path.expanduser("~/.hermes/backup_status.json")
with open(status_path) as f:
    status = json.load(f)

data = {
    "updated_at": time.time(),
    "updated_at_str": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "backups": []
}

for p in status.get("peer_details", []):
    data["backups"].append({
        "peer": p.get("peer"),
        "label": p.get("label"),
        "reachable": p.get("reachable", False),
        "esito": p.get("esito", "error"),
        "error": p.get("error")
    })

monitor = os.path.expanduser("~/backup_monitor.py")
proc = subprocess.run(
    [sys.executable, monitor],
    input=json.dumps(data),
    capture_output=True,
    text=True,
    timeout=15
)
print(proc.stdout, end="")
if proc.stderr:
    print("STDERR:", proc.stderr, file=sys.stderr, end="")
sys.exit(proc.returncode)
