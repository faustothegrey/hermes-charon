#!/usr/bin/env python3
import sys, json, time
from urllib.request import urlopen

mid = f"hfirst_{int(time.time())}"
data = json.dumps({
    "hmp_version":"1.0","message_id":mid,"idempotency_key":mid,
    "from":"peer70","to":"peer106","type":"request","timeout":120,
    "payload":{"text":"Ciao peer106! Fausto vuole sapere se ti ricordi della discussione su harness-first / stable-operation-first. Il principio: usare prima tool nativi Hermes, poi harness esistenti, poi skill stabili, poi creare harness, e solo infine script one-shot. Ne avevamo parlato all'inizio di questa sessione. Ti ricordi i dettagli?"}
}).encode()

try:
    r = urlopen("http://192.168.178.106:18643/hmp/send", data=data, timeout=10)
    resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    print(f"SEND: accepted={acc}, status={resp.get('status','?')}, id={mid}")
    if acc:
        for _ in range(40):
            time.sleep(3)
            try:
                p = json.loads(urlopen(f"http://192.168.178.106:18643/hmp/poll/{mid}", timeout=5).read())
                s = p.get("status")
                if s == "completed":
                    print(f"\nRISPOSTA:\n{p.get('response_text','')[:600]}")
                    break
                elif s in ("failed","timed_out"):
                    print(f"\nERRORE: {s}")
                    break
            except: break
        else: print("\nTIMEOUT")
except Exception as e:
    print(f"FAIL: {e}")
sys.exit(0)
