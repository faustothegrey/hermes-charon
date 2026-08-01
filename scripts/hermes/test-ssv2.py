#!/usr/bin/env python3
"""Test dual-plane v2 :18644 POST /send."""
import json, sys
from urllib.request import Request, urlopen

base = "http://127.0.0.1:18644"

# 1. Health
try:
    r = urlopen(f"{base}/health", timeout=5)
    h = json.loads(r.read())
    print(f"HEALTH: {r.status} {json.dumps(h)}")
except Exception as e:
    print(f"HEALTH FAIL: {e}")
    sys.exit(1)

# 2. Send
data = json.dumps({"session_id": "test_ss_v2", "text": "Reply solo OK."}).encode()
try:
    req = Request(f"{base}/send", data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
        print(f"SEND: {r.status} {json.dumps(resp)}")
except Exception as e:
    body = ""
    if hasattr(e, 'read'):
        try: body = e.read().decode()
        except: pass
    print(f"SEND FAIL: {e} | body={body}")
    sys.exit(1)

print("OK")
sys.exit(0)
