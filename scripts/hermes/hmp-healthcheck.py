#!/usr/bin/env python3
"""
hmp-healthcheck.py — Ping bidirezionale HMP su tutti i peer del cluster
Eseguito ogni ora via cronjob Hermes.
Invia ping HMP (via gateway plugin :18643) a ogni peer, verifica risposta.
"""
import json
import time
import sys
import os
import subprocess
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

# ── Peer HMP gateway servers (tutti su :18643) ──
PEERS = {
    "peer70": {
        "url": "http://127.0.0.1:18643/hmp/send",
        "timeout": 5,
        "role": "coordinatore",
        "desc": "RPi4 Debian 11 — orchestratore 24/7",
    },
    "peer106": {
        "url": "http://192.168.178.106:18643/hmp/send",
        "timeout": 8,
        "role": "worker",
        "desc": "ARMv8 Fedora 30 — web research (Trixie!)",
    },
    "peer84": {
        "url": "http://192.168.178.84:18643/hmp/send",
        "timeout": 8,
        "role": "worker",
        "desc": "N56VV Ubuntu 22.04 — heavy duty (cooling 11-17, 02-03)",
    },
    "peer128": {
        "url": "http://192.168.178.112:18643/hmp/send",
        "timeout": 10,
        "role": "worker",
        "desc": "MacBook Pro macOS — portatile",
    },
}


def hmp_ping(peer_name, peer_info):
    """Send HMP ping via gateway plugin."""
    msg_id = f"hc_{peer_name}_{int(time.time())}"
    payload = json.dumps({
        "type": "text",
        "text": f"HMP healthcheck orario — ping da peer70",
        "sender": "peer70",
    }).encode()
    req = Request(peer_info["url"], data=payload,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=peer_info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            accepted = result.get("accepted", False)
            status = result.get("status", "unknown")
            if accepted:
                return ("ok", f"accepted ({status})")
            else:
                return ("error", f"refused: {result.get('error', '?')}")
    except HTTPError as e:
        if e.code == 413:
            return ("ok", "alive (413 — text too long, but reachable)")
        return ("error", f"HTTP {e.code}")
    except URLError as e:
        return ("error", f"unreachable: {e.reason}")
    except OSError as e:
        return ("error", f"connection failed: {e}")
    except Exception as e:
        return ("error", str(e))


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    online = 0
    total = len(PEERS)

    for peer_name, peer_info in sorted(PEERS.items()):
        status, detail = hmp_ping(peer_name, peer_info)
        if status == "ok":
            online += 1
        results.append((peer_name, peer_info["role"], peer_info["desc"], status, detail))
        time.sleep(0.5)  # piccolo delay tra peer per non saturare

    # ── Output ──
    print(f"🌐 HMP Cluster Healthcheck — {now}")
    print()
    print(f"  {online}/{total} peer online")
    print()
    print(f"  {'Peer':<12} {'Ruolo':<14} {'Stato':<10} {'Dettaglio'}")
    print(f"  {'-'*12} {'-'*14} {'-'*10} {'-'*40}")
    for peer, role, desc, status, detail in results:
        icon = "🟢" if status == "ok" else "🔴"
        peer_label = f"{peer} "
        if peer == "peer106":
            peer_label += "✨"  # Trixie star
        print(f"  {icon} {peer:<10} {role:<14} {status:<10} {detail[:40]}")
    print()
    if online == total:
        print("  ✅ TUTTI I PEER ONLINE")
    else:
        print(f"  ⚠️  {total - online} peer non raggiungibili")


if __name__ == "__main__":
    main()
