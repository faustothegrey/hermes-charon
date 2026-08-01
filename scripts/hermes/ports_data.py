#!/usr/bin/env python3
"""ports_data.py — read port forwarding rules from FRITZ!Box for NetBoard.

Reads via TR-064. Returns a formatted dict.
"""
import json
import time
from pathlib import Path

_cache = None
_cache_time = 0
_CACHE_TTL = 30  # secondi


def get_ports():
    """Return list of port forwarding rules, or empty list."""
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < _CACHE_TTL:
        return _cache

    try:
        from fritzconnection import FritzConnection
        fc = FritzConnection(address="192.168.178.1")
        rules = []
        i = 0
        while True:
            try:
                e = fc.call_action("WANIPConn1", "GetGenericPortMappingEntry", NewPortMappingIndex=i)
                rules.append({
                    "ext_port": int(e["NewExternalPort"]),
                    "protocol": e["NewProtocol"],
                    "internal_ip": e["NewInternalClient"],
                    "internal_port": int(e["NewInternalPort"]),
                    "desc": e.get("NewPortMappingDescription", ""),
                    "enabled": e.get("NewEnabled", False),
                })
                i += 1
            except Exception:
                break
        _cache = rules
        _cache_time = now
        return rules
    except Exception:
        _cache = []
        _cache_time = now
        return []


def format_ports_line(rules, max_len=45):
    """Short one-liner: '📡 2 forwarding: 51413→peer84, 22→peer70'"""
    if not rules:
        return "📡 Nessun port forwarding"

    # Build short descriptions
    parts = []
    # Group by IP + internal port
    grouped = {}
    for r in rules:
        key = (r["internal_ip"], r["internal_port"])
        if key not in grouped:
            desc = r.get("desc", "").lower()
            if "transmission" in desc:
                peer = "peer84"
            elif "hermes" in desc or "ssh" in desc or "guardiano" in desc:
                peer = "peer70"
            else:
                peer = r["internal_ip"].rsplit(".", 1)[-1]
            grouped[key] = {"peer": peer, "ext_ports": [], "protocols": []}
        grouped[key]["ext_ports"].append(str(r["ext_port"]))
        grouped[key]["protocols"].append(r["protocol"])
    
    for (ip, int_port), info in grouped.items():
        ext = "+".join(sorted(set(info["ext_ports"])))
        protos = "+".join(sorted(set(info["protocols"])))
        parts.append(f"{ext}/{protos}→{info['peer']}")

    line = f"📡 {len(rules)} regole: "
    line += ", ".join(parts)
    if len(line) > max_len:
        line = line[:max_len-3] + "..."
    return line


if __name__ == "__main__":
    rules = get_ports()
    print(format_ports_line(rules))
