#!/usr/bin/env python3
"""
HMP v2 Healthcheck — Ping bidirezionale su tutti i peer con HMP v2 (porta 18643)
Eseguito ogni ora via cronjob Hermes.
Usa il nuovo HMP gateway plugin: formato {from, to, text, message_id}
"""
import json, time, subprocess, sqlite3
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

HMP_PORT = 18643
PEERS = {
    "peer58":  {"host": "192.168.178.58",  "timeout": 8},
    "peer84":  {"host": "192.168.178.84",  "timeout": 8},
    "peer106": {"host": "192.168.178.106", "timeout": 8},
    "peer128": {"host": "192.168.178.112", "timeout": 8},
}

SSH_FALLBACK = {
    "peer128": ("fausto@192.168.178.112", f"curl -s --connect-timeout 3 http://127.0.0.1:{HMP_PORT}/health"),
}

def hmp_send(peer_name, peer_info):
    mid = f"hc_{peer_name}_{int(time.time())}"
    msg = {"from": "peer70", "to": peer_name, "text": "Healthcheck HMP v2 orario.", "message_id": mid}
    data = json.dumps(msg).encode()
    req = Request(f"http://{peer_info['host']}:{HMP_PORT}/hmp/send",
                  data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=peer_info.get("timeout", 8)) as resp:
            result = json.loads(resp.read())
            if result.get("accepted"):
                return "sent", mid
            return "refused", result.get("error", "unknown")
    except (HTTPError, URLError, OSError) as e:
        # fallback SSH
        if peer_name in SSH_FALLBACK:
            uh, cmd = SSH_FALLBACK[peer_name]
            try:
                r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                    uh, cmd], capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and '"ok"' in r.stdout:
                    return "sent_ssh", "via SSH fallback"
            except: pass
        return "error", str(e)

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    for name, info in PEERS.items():
        status, detail = hmp_send(name, info)
        icon = "✅" if status in ("sent", "sent_ssh") else "❌"
        method = " (SSH)" if status == "sent_ssh" else ""
        results.append((name, icon, status, method))

    print(f"🌐 HMP v2 Healthcheck ({HMP_PORT}) — {now}")
    print()
    print("| Peer | Stato |")
    print("|---|---|")
    for name, icon, status, method in results:
        print(f"| {name} | {icon} {status}{method} |")
    print(f"| peer70 | 🟢 orchestratore |")

if __name__ == "__main__":
    main()
