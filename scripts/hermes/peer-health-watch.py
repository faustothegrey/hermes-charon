#!/usr/bin/env python3
"""peer-health-watch.py — Monitora tutti i peer via HMP :18643.

Ogni 5 minuti, controlla lo stato di salute di ogni peer.
Silenzioso se tutto ok. Logga cambiamenti (online→offline e viceversa)
nel vault Obsidian e via Telegram.
"""
import json, os, time, sys, urllib.request, urllib.error
from pathlib import Path

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "peer-network" / "peer_health.json"
VAULT_DIR = HOME / "Documents" / "Obsidian Vault" / "Peer Health"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# Peer definition: (name, ip, port)
PEERS = [
    ("peer70",  "127.0.0.1",       18643),
    ("peer84",  "192.168.178.84",  18643),
    ("peer106", "192.168.178.106", 18643),
    ("peer128", "192.168.178.112", 18643),
]

def health(host, port, timeout=5):
    """Check HMP health endpoint. Returns (ok: bool, rtt_ms: float or None)."""
    start = time.time()
    try:
        req = urllib.request.Request(f"http://{host}:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            rtt = (time.time() - start) * 1000
            return data.get("status") == "ok", round(rtt, 1)
    except Exception:
        return False, None

def notify(peer, went_down):
    """Log a state change to Obsidian vault and Telegram."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    date_str = time.strftime("%Y-%m-%d")
    emoji = "🔴" if went_down else "🟢"
    msg = f"{emoji} {peer} {'OFFLINE' if went_down else 'ONLINE'}"

    # Obsidian
    note = VAULT_DIR / f"{date_str}.md"
    with open(note, "a") as f:
        f.write(f"- {now[11:16]} | {emoji} {peer} {'OFFLINE' if went_down else 'ONLINE'}\n")

    # Telegram
    tg_token = None
    env_file = HOME / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().split("\n"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tg_token = line.split("=", 1)[1].strip().strip("'\"")
                break
    if tg_token:
        try:
            data = json.dumps({
                "chat_id": "8508115936",
                "text": f"[peer-watch] {msg}",
                "disable_notification": True
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

# Load previous state
previous = {}
if STATE_FILE.exists():
    try:
        previous = {d["name"]: d["online"] for d in json.loads(STATE_FILE.read_text())}
    except: pass

# Check all peers
results = []
for name, host, port in PEERS:
    ok, rtt = health(host, port)
    was_online = previous.get(name, None)
    results.append({"name": name, "online": ok, "rtt_ms": rtt, "host": host, "port": port})

    # Detect transitions
    if was_online is not None and was_online != ok:
        notify(name, went_down=not ok)
        if ok:
            print(f"🟢 {name} tornato online (RTT {rtt}ms)")
        else:
            print(f"🔴 {name} andato OFFLINE")
    elif not ok:
        print(f"🔴 {name} offline (confermato)")
    else:
        # Healthy and stable — silent
        pass

# Save state
STATE_FILE.write_text(json.dumps(results, indent=2))

# Totals
online_count = sum(1 for r in results if r["online"])
print(f"✅ Peer health: {online_count}/{len(results)} online")
