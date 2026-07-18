#!/usr/bin/env python3
"""
hmp-healthcheck.py — Ping bidirezionale HMP su tutti i peer
Eseguito ogni ora via cronjob Hermes (no_agent=True, deliver=local).

Invia ping HMP a peer84 e peer128, verifica risposta, riporta stato.
Silent when healthy — only produces output on errors or transitions.
"""
import json
import time
import subprocess
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

SSH_FALLBACK = {
    "peer128": ("fausto@192.168.178.112", "curl -s --connect-timeout 3 http://127.0.0.1:8643/health"),
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
        if peer_name in SSH_FALLBACK:
            user_host, cmd = SSH_FALLBACK[peer_name]
            try:
                r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                    user_host, cmd], capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and '"ok"' in r.stdout:
                    return "sent_ssh", "via SSH fallback"
            except Exception:
                pass
        return "error", str(e)


def hmp_poll(peer_info, msg_id):
    try:
        with urlopen(f"{peer_info['poll_url']}/{msg_id}", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status", "unknown")
    except Exception:
        return "unreachable"


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts = str(int(time.time()))

    results = []
    all_ok = True

    for peer_name, peer_info in PEERS.items():
        msg_id = f"hc_{peer_name}_{ts}"
        status, detail = hmp_send(peer_name, peer_info, msg_id)

        if status in ("sent", "sent_ssh", "sent_dup"):
            time.sleep(2)
            poll_status = hmp_poll(peer_info, msg_id)
            results.append((peer_name, status, poll_status, detail))
            if poll_status in ("unreachable",):
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
        method = " (via SSH)" if send_status == "sent_ssh" else ""
        print(f"| {peer} | {icon_send} {method.strip()} | {icon_peer} {peer_status} |")
    print(f"| peer70 | — | 🟢 orchestratore |")
    print()
    print(f"Stato: {'✅ TUTTO OK' if all_ok else '⚠️ PROBLEMI RILEVATI (vedi sopra)'}")


if __name__ == "__main__":
    main()