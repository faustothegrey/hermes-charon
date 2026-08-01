#!/usr/bin/env python3
"""lan-monitor.py — Periodic LAN device monitor.

Runs every 10 minutes via cron. Logs changes in LAN device status
(online/offline transitions) to ~/.hermes/netboard/lan_history.jsonl.
"""
import json, os, time
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import fritzbox_data

HISTORY_FILE = Path.home() / ".hermes" / "netboard" / "lan_history.jsonl"
STATE_FILE = Path.home() / ".hermes" / "netboard" / "lan_state.json"
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

# Load previous state
previous = {}
if STATE_FILE.exists():
    try:
        for d in json.loads(STATE_FILE.read_text()):
            previous[d["name"]] = d.get("online", False)
    except: pass

# Fetch current state
devices = fritzbox_data.get_lan_devices()
current = {d["name"]: d.get("online", False) for d in devices}

# Detect changes
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
for name, online in current.items():
    was = previous.get(name)
    if was is not None and was != online:
        entry = {"ts": now, "device": name, "went": "online" if online else "offline"}
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"🔄 {name}: {'🟢 online' if online else '🔴 offline'}")
        # Log to Obsidian vault
        vault = Path.home() / "Documents" / "Obsidian Vault" / "LAN Events"
        vault.mkdir(parents=True, exist_ok=True)
        date_str = time.strftime("%Y-%m-%d")
        note = vault / f"{date_str}.md"
        emoji = "🟢" if online else "🔴"
        with open(note, "a") as f:
            f.write(f"- {now[:16]} | {emoji} {name} {'online' if online else 'offline'}\n")
        print(f"  📝 Loggato in Obsidian: LAN Events/{date_str}.md")

# Save current state
STATE_FILE.write_text(json.dumps(devices, indent=2))
print(f"✅ LAN scan: {len(devices)} devices ({sum(1 for d in devices if d.get('online'))} online)")
