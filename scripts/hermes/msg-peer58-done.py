#!/usr/bin/env python3
import sys, json
from urllib.request import Request, urlopen

mid = f"done58_{int(__import__('time').time())}"
data = json.dumps({"hmp_version":"1.0","message_id":mid,"from":"peer70","to":"peer58","type":"request","timeout":30,"payload":{"text":"peer58 ha finito."}}).encode()
try:
    r = urlopen("http://192.168.178.58:18643/hmp/send", data=data, timeout=10)
    print(f"SENT: {r.read().decode().strip()[:100]}")
except Exception as e:
    print(f"FAIL: {e}")
sys.exit(0)
