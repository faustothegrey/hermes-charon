#!/usr/bin/env python3
"""hmp-healthcheck-terse.py — HMP ping senza SSH fallback, per cron."""
import json, time, sys, os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer84":  {"url": "http://192.168.178.84:8643/hmp/send", "poll_url": "http://192.168.178.84:8643/hmp/poll", "timeout": 8},
    "peer128": {"url": "http://192.168.178.112:8643/hmp/send", "poll_url": "http://192.168.178.112:8643/hmp/poll", "timeout": 15},
}

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ts = str(int(time.time()))
results = []
all_ok = True

for name, info in PEERS.items():
    msg_id = f"hc_{name}_{ts}"
    msg = {
        "hmp_version": "1.0", "message_id": msg_id, "idempotency_key": msg_id,
        "from": "peer70", "to": name, "type": "request",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeout": 30,
        "payload": {"task_type": "ping", "instruction": "Healthcheck HMP orario. Rispondi con ACK."}
    }
    data = json.dumps(msg).encode()
    req = Request(info["url"], data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            send_status = "sent_dup" if result.get("duplicate") else "sent"
            mid = result["message_id"]
    except (HTTPError, URLError, OSError) as e:
        send_status = "error"
        mid = str(e)
        all_ok = False

    if send_status in ("sent", "sent_dup"):
        time.sleep(2)
        try:
            with urlopen(f"{info['poll_url']}/{msg_id}", timeout=5) as resp:
                poll_data = json.loads(resp.read())
            peer_status = poll_data.get("status", "unknown")
        except Exception:
            peer_status = "unreachable"
            all_ok = False
    else:
        peer_status = mid

    results.append((name, send_status, peer_status))

# Output
print(f"🌐 HMP Healthcheck — {now}")
print()
print("| Peer | Invio | Stato HMP |")
print("|---|---|---|")
for peer, send, pstat in results:
    icon_send = "✅" if send in ("sent", "sent_ssh", "sent_dup") else "❌"
    icon_peer_s = "🟢" if pstat in ("delivered", "working", "pending", "ok") else "🔴"
    print(f"| {peer} | {icon_send} | {icon_peer_s} {pstat} |")
print("| peer70 | — | 🟢 orchestratore |")
print()
print(f"Stato: {'✅ TUTTO OK' if all_ok else '⚠️ PROBLEMI RILEVATI (vedi sopra)'}")
