#!/usr/bin/env python3
"""Invia messaggio HMP diretto a peer136 e fa poll."""
import json, time, sys
from urllib.request import Request, urlopen

dst = "192.168.178.136"
mid = f"cl136_{int(time.time())}"
payload = json.dumps({
    "hmp_version": "1.0", "message_id": mid, "idempotency_key": mid,
    "from": "peer70", "to": "peer136", "type": "request", "timeout": 120,
    "payload": {"text": "Ciao peer136! peer70 chiede: controlla se nella tua memoria ci sono riferimenti al vecchio HMP v1 (porta 8643, hmp.py standalone). Se li trovi, cancellali. Tieni solo HMP v2 su 18643. Riporta cosa hai fatto."}
}).encode()

try:
    req = Request(f"http://{dst}:18643/hmp/send", data=payload, headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    print(f"✅ peer136: accepted={acc}, status={resp.get('status','?')}, id={mid}")
    if acc:
        for _ in range(30):
            time.sleep(3)
            try:
                with urlopen(f"http://{dst}:18643/hmp/poll/{mid}", timeout=5) as pr:
                    poll = json.loads(pr.read())
                s = poll.get("status")
                if s == "completed":
                    print(f"\n📬 {poll.get('response_text','')}"); sys.exit(0)
                elif s in ("failed","timed_out","cancelled"):
                    print(f"\n❌ {s}: {poll.get('error','?')}"); sys.exit(1)
            except Exception as e:
                print(f"   poll error: {e}")
                break
        print("\n⏱ Timeout")
    else:
        print(f"❌ Rifiutato: {resp.get('error','?')}")
except Exception as e:
    print(f"❌ {e}")
    sys.exit(1)
