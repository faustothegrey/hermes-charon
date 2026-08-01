#!/usr/bin/env python3
import sys, json, time
from urllib.request import Request, urlopen
from datetime import datetime

mid = f"deploy58_{int(time.time())}"
text = """DEPLOY dual-plane v2.0.0 su peer58

Steps:
1) mkdir -p ~/.hermes/scripts
2) SCP da peer70 (192.168.178.70):
   scp fausto@192.168.178.70:.hermes/scripts/hmp_dual_plane_light.py ~/.hermes/scripts/
   scp fausto@192.168.178.70:.hermes/scripts/hmp_dual_plane.py ~/.hermes/scripts/

3) Avvia server in background:
   cd ~/.hermes/scripts && python3 -c 'from hmp_dual_plane import run_server; run_server(port=18644, node_id="peer58")' &

4) CONFERMA che /health risponde:
   curl -sf http://localhost:18644/health

Quando hai finito, rispondi con CONFERMA e l'output di /health."""

data = json.dumps({
    "hmp_version": "1.0", "message_id": mid, "idempotency_key": mid,
    "from": "peer70", "to": "peer58", "type": "request", "timeout": 300,
    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "payload": {"text": text}
}).encode()

try:
    r = urlopen("http://192.168.178.58:18643/hmp/send", data=data, timeout=10)
    resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    print(f"SEND: accepted={acc}, status={resp.get('status','?')}, id={mid}")
    if acc:
        for _ in range(60):
            time.sleep(5)
            try:
                p = json.loads(urlopen(f"http://192.168.178.58:18643/hmp/poll/{mid}", timeout=5).read())
                s = p.get("status")
                if s == "completed":
                    print(f"\nRISPOSTA da peer58:\n{p.get('response_text','')[:500]}")
                    break
                elif s in ("failed","timed_out","cancelled"):
                    print(f"\nERRORE: {s} {p.get('error','?')}")
                    break
            except: break
        else:
            print("\nTIMEOUT after 300s")
except Exception as e:
    print(f"FAIL: {e}")
sys.exit(0)
