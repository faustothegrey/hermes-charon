#!/usr/bin/env python3
"""backup_data.py — read backup status for NetBoard.

Reads ~/.hermes/peer-network/backup_status.json (written by backup_monitor.py cron).
Returns a formatted dict or None if unavailable.
"""

import json
import time
from pathlib import Path

STATUS_FILE = Path.home() / ".hermes/peer-network/backup_status.json"

# Stale after 90 minutes (3 missed 30-min ticks)
STALE_AFTER = 90 * 60


def get_status():
    """Return backup status dict or None."""
    try:
        if not STATUS_FILE.exists():
            return None
        data = json.loads(STATUS_FILE.read_text())
        age = time.time() - data.get("updated_at", 0)
        return {
            "available": True,
            "stale": age > STALE_AFTER,
            "age_sec": int(age),
            "backups": data.get("backups", []),
        }
    except (json.JSONDecodeError, Exception):
        return None


def format_short(status):
    """One-liner for framebuffer bottom area."""
    if status is None:
        return "💾 Backup: nessun dato"
    if not status.get("available"):
        return "💾 Backup: N/D"

    parts = []
    for b in status.get("backups", []):
        peer_short = b.get("peer", "?")
        esito = b.get("esito", "?")
        ora = ""
        if b.get("ultimo_run"):
            ora = b["ultimo_run"][-8:-3] if len(b["ultimo_run"]) >= 8 else b["ultimo_run"]
        icon = {"success": "✅", "error": "❌", "running": "🔄", "offline": "⭕", "never-ran": "⚪"}.get(esito, "❓")
        parts.append(f"{icon}{peer_short}{' ' + ora if ora else ''}")

    line = "  ".join(parts)
    stale = " ⚠ stale" if status.get("stale") else ""
    return f"💾 {line}{stale}"


if __name__ == "__main__":
    s = get_status()
    print(json.dumps(s, indent=2) if s else "None")
    print()
    print(format_short(s))