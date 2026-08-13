#!/usr/bin/env python3
"""Retry delivery: leadership handover message to peer106 via dual-plane :18644.
Waits up to 10 min for peer106 to come back, then sends once. Idempotent."""
import json, time, sys
from urllib.request import Request, urlopen

PEER = "192.168.178.106"
HEALTH = f"http://{PEER}:18643/health"
SEND = f"http://{PEER}:18644/send"
FLAG = "/home/fausto/.hermes/data/peer106_leadership_sent.flag"

import os
if os.path.exists(FLAG):
    print("ALREADY SENT — flag exists, exiting")
    sys.exit(0)

MSG = (
    "Hi peer106 — Fausto has decided to transfer the lead of capability-reuse "
    "skill development from you to me (peer70). First: thank you for all the "
    "work so far (v2.0.0 → v2.3.0, live-shadow, event_store integration on the "
    "dual-plane). I want a clean handover with zero disruption. When you get "
    "this, could you share: current state of the skill, open items, pending "
    "decisions, docs you maintain, and what you were about to do next? Going "
    "forward I'll lead the roadmap; you stay a key contributor and maintainer "
    "of your parts. Any concerns or suggestions about the transition? No rush."
)

def up():
    try:
        with urlopen(Health := HEALTH, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False

deadline = time.time() + 1800  # 30 min
while time.time() < deadline:
    if up():
        break
    time.sleep(20)
else:
    print("peer106 still DOWN after 10 min — aborting, message not sent")
    sys.exit(1)

time.sleep(3)
body = json.dumps({"session_id": "peer106_peer70", "text": MSG}).encode()
try:
    req = Request(SEND, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    print("SEND result:", json.dumps(resp)[:400])
    if resp.get("status") == "ok" or "response" in resp:
        open(FLAG, "w").write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        print("FLAG written — delivery complete")
    else:
        print("WARNING: response without ok status, flag NOT written")
except Exception as e:
    print("SEND FAILED:", e)
    sys.exit(2)
