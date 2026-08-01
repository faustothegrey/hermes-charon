#!/usr/bin/env python3
"""Ultra-simple test of server-side v2 :18644"""
import json, sys, traceback
from urllib.request import Request, urlopen

try:
    # 1. Health
    r = urlopen("http://127.0.0.1:18644/health", timeout=5)
    health = json.loads(r.read())
    print(f"HEALTH OK: {health}")

    # 2. Send
    data = json.dumps({"session_id": "testv2", "text": "ping"}).encode()
    req = Request("http://127.0.0.1:18644/send", data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=60) as r2:
        resp = json.loads(r2.read())
        print(f"SEND OK: {resp}")
    print("OK")
except Exception:
    print(f"FAIL: {traceback.format_exc()}")
    sys.exit(1)
