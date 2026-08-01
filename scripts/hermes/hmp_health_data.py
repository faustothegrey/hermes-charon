#!/usr/bin/env python3
"""hmp_health_data.py — read HMP health status for NetBoard.

Reads ~/.hermes/peer-network/hmp_health_status.json (written by hmp-ping-round.py cron).
Returns a formatted dict per peer, keyed by peer name.
"""

import json
import time
from pathlib import Path
from typing import Optional

STATUS_FILE = Path.home() / ".hermes" / "peer-network" / "hmp_health_status.json"
# Stale after 30 minutes (3 missed 10-min ticks)
STALE_AFTER = 30 * 60


def get_status() -> Optional[dict]:
    """Return dict of {peer_name: {hmp_status...}} or None."""
    try:
        if not STATUS_FILE.exists():
            return None
        data = json.loads(STATUS_FILE.read_text())
        age = time.time() - data.get("updated_at", 0)
        if age > STALE_AFTER:
            return {"stale": True, "age_sec": int(age), "peers": {}}
        
        peers = {}
        for p in data.get("peers", []):
            peers[p["name"]] = {
                "reachable": p["hmp"].get("reachable", False),
                "ms": p["hmp"].get("ms"),
                "self": p["hmp"].get("self", False),
                "error": p["hmp"].get("error", ""),
                "probed_at": p.get("probed_at", ""),
            }
        return {
            "stale": False,
            "age_sec": int(age),
            "all_reachable": data.get("all_reachable", False),
            "updated_at_iso": data.get("updated_at_iso", ""),
            "peers": peers,
        }
    except (json.JSONDecodeError, Exception):
        return None


def hmp_status_for(peer_name: str, status: Optional[dict]) -> Optional[str]:
    """Return a short HMP status string for a given peer name."""
    if status is None or status.get("stale"):
        return None
    peer = status.get("peers", {}).get(peer_name)
    if peer is None:
        return None
    if peer.get("self"):
        return "HMP●"
    if peer.get("reachable"):
        ms = peer.get("ms")
        if ms is not None and ms < 200:
            return f"HMP● {ms:.0f}ms"
        elif ms is not None:
            return f"HMP◒ {ms:.0f}ms"
        return "HMP●"
    else:
        return "HMP✗"
