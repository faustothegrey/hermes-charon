#!/usr/bin/env python3
"""HMP Healthcheck — vero ping HMP v2 via /hmp/send + poll.
Invia un messaggio HMP a ogni peer e verifica che venga accettato.
Nessuna subprocess, solo urllib."""
import json
import time
import urllib.request
from urllib.error import URLError, HTTPError
from datetime import datetime

PEERS = {
    "peer84":  "192.168.178.84",
    "peer106": "192.168.178.106",
    "peer128": "192.168.178.112",
}

now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
ts = str(int(time.time()))
ok = 0
total = len(PEERS)
lines = []

for pid, ip in sorted(PEERS.items()):
    msg_id = f"hc_{pid}_{ts}"
    envelope = json.dumps({
        "hmp_version": "1.0",
        "message_id": msg_id,
        "idempotency_key": msg_id,
        "from": "peer70",
        "to": pid,
        "type": "request",
        "timestamp": now,
        "timeout": 30,
        "payload": {"text": "PING HMP healthcheck orario"},
    }).encode()

    try:
        req = urllib.request.Request(
            f"http://{ip}:18643/hmp/send",
            data=envelope,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            resp = json.loads(r.read())

        accepted = resp.get("accepted", resp.get("status") == "queued")
        if accepted:
            ok += 1
            status = resp.get("status", "accepted")
            lines.append(f"  ✅ {pid:<10} {ip:<18} HMP send OK ({status})")
        else:
            lines.append(f"  ❌ {pid:<10} {ip:<18} HMP refused: {resp.get('error', '?')}")
    except HTTPError as e:
        if e.code == 413:
            # 413 = alive but text too long — comunque risponde!
            ok += 1
            lines.append(f"  ⚠️ {pid:<10} {ip:<18} alive (413 — text too long)")
        else:
            lines.append(f"  ❌ {pid:<10} {ip:<18} HTTP {e.code}")
    except URLError as e:
        lines.append(f"  ❌ {pid:<10} {ip:<18} URLError: {e.reason}")
    except OSError as e:
        lines.append(f"  ❌ {pid:<10} {ip:<18} OSError: {e}")
    except Exception as e:
        lines.append(f"  ❌ {pid:<10} {ip:<18} {type(e).__name__}: {str(e)[:50]}")

    time.sleep(0.3)  # piccolo delay tra peer

print(f"🌐 HMP Healthcheck — {now} (via HMP send)")
print()
print("  Peer         IP                Risultato")
print("  " + "-"*55)
print("\n".join(lines))
print()
if ok == total:
    print(f"  ✅ {ok}/{total} peer online — TUTTI RAGGIUNGIBILI VIA HMP")
else:
    print(f"  ⚠️  {ok}/{total} peer online — {total-ok} non rispondono via HMP")
