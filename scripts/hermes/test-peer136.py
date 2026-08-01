#!/usr/bin/env python3
"""Check peer136 + send HMP message. Non-zero exit only if script itself crashes."""
import json, time, sys
from urllib.request import Request, urlopen

dst = "192.168.178.136"
results = []

# 1) Health check
try:
    req = Request(f"http://{dst}:18643/health")
    with urlopen(req, timeout=5) as r:
        h = r.read().decode().strip()[:80]
        results.append(f"✅ Health: {h}")
except Exception as e:
    results.append(f"❌ Health: {e}")

# 2) HMP send
try:
    mid = f"cl136_{int(time.time())}"
    payload = json.dumps({
        "hmp_version": "1.0", "message_id": mid, "idempotency_key": mid,
        "from": "peer70", "to": "peer136", "type": "request", "timeout": 120,
        "payload": {"text": "Ciao peer136! peer70 chiede: controlla se nella tua memoria ci sono riferimenti al vecchio HMP v1 (porta 8643, hmp.py standalone). Se li trovi, cancellali. Tieni solo HMP v2 su 18643. Riporta cosa hai fatto."}
    }).encode()
    req = Request(f"http://{dst}:18643/hmp/send", data=payload, headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    results.append(f"✅ HMP send: accepted={acc}, status={resp.get('status','?')}")
    if acc:
        for _ in range(20):
            time.sleep(3)
            try:
                with urlopen(f"http://{dst}:18643/hmp/poll/{mid}", timeout=5) as pr:
                    poll = json.loads(pr.read())
                s = poll.get("status")
                if s == "completed":
                    results.append(f"📬 Risposta: {poll.get('response_text','')[:200]}")
                    break
                elif s in ("failed","timed_out","cancelled"):
                    results.append(f"❌ Poll: {s} {poll.get('error','?')}")
                    break
            except: break
        else:
            results.append("⏱ Poll timeout")
    else:
        results.append(f"❌ Rifiutato: {resp}")
except Exception as e:
    results.append(f"❌ HMP send error: {e}")

print("\n".join(results))
sys.exit(0)
