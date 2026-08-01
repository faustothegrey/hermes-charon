#!/usr/bin/env python3
"""Invia messaggio HMP a peer136 e fa poll per la risposta."""
import json, time, sys, os
from urllib.request import Request, urlopen
from urllib.error import URLError

msg_id = f"cl136_{int(time.time())}"
payload = json.dumps({
    "hmp_version": "1.0",
    "message_id": msg_id,
    "idempotency_key": msg_id,
    "from": "peer70",
    "to": "peer136",
    "type": "request",
    "timeout": 120,
    "payload": {"text": "Ciao peer136! peer70 chiede: controlla se nella tua memoria ci sono riferimenti al vecchio HMP v1 (porta 8643, hmp.py standalone). Se li trovi, cancellali. Tieni solo HMP v2 su 18643. Riporta cosa hai fatto."}
}).encode()

try:
    req = Request("http://127.0.0.1:18643/hmp/send", data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())
    accepted = resp.get("accepted") or resp.get("status") == "queued"
    print(f"✅ Inviato a peer136: accepted={accepted}, status={resp.get('status','?')}, msg_id={msg_id}")
    if accepted:
        # Poll per la risposta
        for i in range(30):
            time.sleep(3)
            try:
                with urlopen(f"http://127.0.0.1:18643/hmp/poll/{msg_id}", timeout=5) as pr:
                    poll = json.loads(pr.read())
                s = poll.get("status")
                if s in ("completed",):
                    rt = poll.get("response_text", "")
                    print(f"\n📬 Risposta da peer136:\n{rt}")
                    break
                elif s in ("failed", "timed_out", "cancelled"):
                    print(f"\n❌ peer136: {s} — {poll.get('error','?')}")
                    break
                elif i % 5 == 0:
                    print(f"   Poll... stato={s}")
            except Exception as e:
                print(f"   Poll error: {e}")
                break
        else:
            print(f"\n⚠️ Timeout poll dopo 90s")
except Exception as e:
    print(f"❌ Errore invio a peer136: {e}")
    sys.exit(1)
