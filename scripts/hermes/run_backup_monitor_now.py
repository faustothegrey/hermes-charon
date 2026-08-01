#!/usr/bin/env python3
"""Run the backup monitor: read input, persist status."""
import json, os, datetime

DATA_FILE = os.path.expanduser("~/.hermes/backup_input.json")
STATUS_FILE = os.path.expanduser("~/.hermes/backup_status.json")

with open(DATA_FILE) as f:
    data = json.load(f)

updated_at = data.get("updated_at")
updated_at_str = data.get("updated_at_str",
                          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
backups = data.get("backups", [])

total = len(backups)
errors = [b for b in backups if b.get("esito") == "error"]
ok = [b for b in backups if b.get("esito") == "ok"]

status = {
    "timestamp": datetime.datetime.now().isoformat(),
    "updated_at": updated_at,
    "updated_at_str": updated_at_str,
    "total_peers": total,
    "ok": len(ok),
    "errors": len(errors),
    "unreachable": len(errors),
    "peer_details": [
        {
            "peer": b.get("peer"),
            "label": b.get("label"),
            "reachable": b.get("reachable", False),
            "esito": b.get("esito"),
            "error": b.get("error"),
        }
        for b in backups
    ],
}

os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
with open(STATUS_FILE, "w") as f:
    json.dump(status, f, indent=2, ensure_ascii=False)

print(f"[OK] Status persisted to {STATUS_FILE}")
print(f"      Peers: {total} total, {len(ok)} ok, {len(errors)} error/unreachable")
