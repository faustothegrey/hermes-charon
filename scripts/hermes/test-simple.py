#!/usr/bin/env python3
print("test-peer136 starting")
import sys
from urllib.request import Request, urlopen
print("imports ok")
dst = "192.168.178.136"
try:
    req = Request(f"http://{dst}:18643/health")
    with urlopen(req, timeout=5) as r:
        print(f"HEALTH: {r.read().decode().strip()}")
except Exception as e:
    print(f"HEALTH FAIL: {e}")
try:
    mid = f"t{int(time.time())}"
    data = ('{"hmp_version":"1.0","message_id":"'+mid+'","from":"peer70","to":"peer136","type":"request","timeout":60,"payload":{"text":"Hello peer136"}}').encode()
    req = Request(f"http://{dst}:18643/hmp/send", data=data, headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=10) as r:
        print(f"SEND: {r.read().decode().strip()[:100]}")
except Exception as e:
    print(f"SEND FAIL: {e}")
sys.exit(0)
