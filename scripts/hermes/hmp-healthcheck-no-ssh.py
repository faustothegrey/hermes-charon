#!/usr/bin/env python3
"""
hmp-healthcheck-no-ssh.py — Ping bidirezionale HMP (senza SSH fallback)
Versione cron-safe per evitare blocchi di sicurezza.
"""
import json
import time
import sys
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer84": {
        "url": "http://192.168.178.84:8643/hmp/send",
        "poll_url": "http://192.168.178.84:8643/hmp/poll",
        "timeout": 8,
    },
    "peer128": {
        "url": "http://192.168.178.112:8643/hmp/send",
        "poll_url": "http://192.168.178.112:8643/hmp/poll",
        "timeout": 15,
    },
}


def hmp_send(peer_name, peer_info, msg_id):
    msg = {
        "hmp_version": "1.0",
        "message_id": msg_id,
        "idempotency_key": msg_id,
        "from": "peer70",
        "to": peer_name,
        "type": "request",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeout": 30,
        "payload": {"task_type": "ping", "instruction": "Healthcheck HMP orario. Rispondi con ACK."}
    }
    data = json.dumps(msg).encode()
    req = Request(peer_info["url"], data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=peer_info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            if result.get("duplicate"):
                return "sent_dup", result["message_id"]
            return "sent", result["message_id"]
    except (HTTPError, URLError, OSError) as e:
        return "error", str(e)


def hmp_poll(peer_info, msg_id):
    try:
        with urlopen(f"{peer_info['poll_url']}/{msg_id}", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status", "unknown")
    except Exception as e:
        return f"unreachable ({e})"


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_suffix = str(int(time.time()))

    results = []
    all_ok = True

    for peer_name, peer_info in PEERS.items():
        msg_id = f"hc_{peer_name}_{timestamp_suffix}"
        status, detail = hmp_send(peer_name, peer_info, msg_id)

        if status in ("sent", "sent_ssh", "sent_dup"):
            time.sleep(2)
            poll_status = hmp_poll(peer_info, msg_id)
            results.append((peer_name, status, poll_status, detail))
            if "unreachable" in str(poll_status):
                all_ok = False
        else:
            results.append((peer_name, "error", detail, ""))
            all_ok = False

    print(f"🌐 HMP Healthcheck — {now}")
    print()
    print("| Peer | Invio | Stato HMP |")
    print("|---|---|---|")
    for peer, send_status, peer_status, mid in results:
        icon_send = "✅" if send_status in ("sent", "sent_ssh", "sent_dup") else "❌"
        icon_peer = "🟢" if peer_status in ("delivered", "working", "pending", "ok") else "🔴"
        print(f"| {peer} | {icon_send}  | {icon_peer} {peer_status} |")
    print(f"| peer70 | — | 🟢 orchestratore |")
    print()
    print(f"Stato: {'✅ TUTTO OK' if all_ok else '⚠️ PROBLEMI RILEVATI (vedi sopra)'}")

    # Export results for logging
    os.environ["HMP_RESULT"] = "OK" if all_ok else "PROBLEMS"
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
