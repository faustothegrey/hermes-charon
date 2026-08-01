#!/usr/bin/env python3
"""
hmp-healthcheck-urllib.py — Pure urllib HMP healthcheck (no subprocess/SSH).
"""
import json, time, sys, os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer84": {"url": "http://192.168.178.84:8643/hmp/send", "poll_url": "http://192.168.178.84:8643/hmp/poll", "timeout": 8},
    "peer128": {"url": "http://192.168.178.112:8643/hmp/send", "poll_url": "http://192.168.178.112:8643/hmp/poll", "timeout": 15},
}

def hmp_send(peer_name, info, msg_id):
    msg = {
        "hmp_version": "1.0", "message_id": msg_id, "idempotency_key": msg_id,
        "from": "peer70", "to": peer_name, "type": "request",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeout": 30, "payload": {"task_type": "ping", "instruction": "Healthcheck HMP orario. Rispondi con ACK."}
    }
    data = json.dumps(msg).encode()
    req = Request(info["url"], data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            if result.get("duplicate"):
                return "sent_dup", result["message_id"]
            return "sent", result["message_id"]
    except (HTTPError, URLError, OSError) as e:
        return "error", str(e)

def hmp_poll(info, msg_id):
    try:
        with urlopen(f"{info['poll_url']}/{msg_id}", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status", "unknown")
    except Exception as e:
        return f"unreachable ({e})"

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts = str(int(time.time()))
    results = []
    all_ok = True
    for name, info in PEERS.items():
        mid = f"hc_{name}_{ts}"
        status, detail = hmp_send(name, info, mid)
        if status in ("sent", "sent_dup"):
            time.sleep(2)
            pstatus = hmp_poll(info, mid)
            results.append((name, status, pstatus, detail))
            if "unreachable" in pstatus or "error" in pstatus:
                all_ok = False
        else:
            results.append((name, "error", detail, ""))
            all_ok = False
    print(f"🌐 HMP Healthcheck — {now}")
    print()
    print("| Peer | Invio | Stato HMP |")
    print("|---|---|---|")
    for peer, s, ps, mid in results:
        icon_s = "✅" if s in ("sent", "sent_dup") else "❌"
        icon_p = "🟢" if ps in ("delivered", "working", "pending", "ok") else "🔴"
        print(f"| {peer} | {icon_s} | {icon_p} {ps} |")
    print(f"| peer70 | — | 🟢 orchestratore |")
    print()
    print(f"Stato: {'✅ TUTTO OK' if all_ok else '⚠️ PROBLEMI RILEVATI (vedi sopra)'}")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
