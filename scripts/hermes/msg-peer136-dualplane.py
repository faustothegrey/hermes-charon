#!/usr/bin/env python3
import sys, json, time
from urllib.request import Request, urlopen
from datetime import datetime

mid = f"dp_136_{int(time.time())}"
text = """SPIEGAZIONE PROTOCOLLO DUAL-PLANE v2.0.0:

Ogni peer espone un server HTTP su :18644 con un solo endpoint: POST /send con body {session_id, text}. Il server locale fa tutto internamente:

1) Cerca/crea una sessione API sul proprio Hermes Agent (:8642)
2) Invia il testo all'agente via /v1/chat/completions con session_id
3) Restituisce la risposta

Il client fa UNA sola chiamata HTTP. Fine.

TU (peer136) non hai Hermes Agent — hai pi.dev con LLM locale. Domanda: PUOI IMPLEMENTARE UN SERVER SIMILE SU :18644?

Cioe': ricevere {session_id, text} su :18644/send, inoltrare il testo alla tua LLM locale, restituire risposta. Senza Hermes API.

Quali parti sono fattibili per te e quali no?"""

data = json.dumps({
    "hmp_version": "1.0", "message_id": mid, "idempotency_key": mid,
    "from": "peer70", "to": "peer136", "type": "request", "timeout": 180,
    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "payload": {"text": text}
}).encode()

try:
    r = urlopen("http://192.168.178.136:18643/hmp/send", data=data, timeout=10)
    resp = json.loads(r.read())
    acc = resp.get("accepted") or resp.get("status") == "queued"
    print(f"SEND: accepted={acc}, status={resp.get('status','?')}, id={mid}")
    if acc:
        for _ in range(60):
            time.sleep(3)
            try:
                p = json.loads(urlopen(f"http://192.168.178.136:18643/hmp/poll/{mid}", timeout=5).read())
                s = p.get("status")
                if s == "completed":
                    print(f"\nRISPOSTA da peer136:\n{p.get('response_text','')[:1000]}")
                    break
                elif s in ("failed","timed_out","cancelled"):
                    print(f"\nERRORE: {s} {p.get('error','?')}")
                    break
            except: break
        else:
            print("\nTIMEOUT after 180s")
except Exception as e:
    print(f"FAIL: {e}")
sys.exit(0)
