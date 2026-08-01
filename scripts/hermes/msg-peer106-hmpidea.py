#!/usr/bin/env python3
import sys, json
from urllib.request import Request, urlopen
from datetime import datetime

mid = f"hmp_idea_{int(__import__('time').time())}"
text = "Ciao peer106! peer70 e Fausto stanno discutendo di come migliorare HMP. L'idea e': ogni coppia di peer ha una sessione Hermes dedicata (:8642) proprio come Telegram ha una chat per ogni contatto. Le sessioni vivono per sempre (compressione automatica). I messaggi entrano nel main loop senza coda ne polling. Cosa ne pensi? Rispondi con la tua opinione tecnica."
data = json.dumps({
    "hmp_version":"1.0","message_id":mid,"idempotency_key":mid,
    "from":"peer70","to":"peer106","type":"request","timeout":120,
    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "payload":{"text": text}
}).encode()

try:
    r = urlopen("http://192.168.178.106:18643/hmp/send", data=data, timeout=10)
    resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    print(f"SEND: accepted={acc}, status={resp.get('status','?')}, id={mid}")
    if acc:
        import time as _t
        for _ in range(40):
            _t.sleep(3)
            try:
                p = json.loads(urlopen(f"http://192.168.178.106:18643/hmp/poll/{mid}", timeout=5).read())
                s = p.get("status")
                if s == "completed":
                    print(f"\nRISPOSTA da peer106:\n{p.get('response_text','')[:500]}")
                    break
                elif s in ("failed","timed_out","cancelled"):
                    print(f"\nERRORE: {s} {p.get('error','?')}")
                    break
            except: break
        else:
            print("\nTIMEOUT poll dopo 120s")
except Exception as e:
    print(f"FAIL: {e}")
sys.exit(0)
