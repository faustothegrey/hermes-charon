#!/usr/bin/env python3
import sys, json, time
from urllib.request import Request, urlopen
print("=== Script started ===")
sys.stdout.flush()
# Probe peer136
ip = "192.168.178.136"
print(f"Pinging {ip}:18643/health...")
try:
    r = urlopen(f"http://{ip}:18643/health", timeout=5)
    print(f"Health: {r.read().decode().strip()[:80]}")
except Exception as e:
    print(f"Health failed: {type(e).__name__}: {e}")
# Try send
try:
    mid = f"cl136_{int(time.time())}"
    body = json.dumps({"hmp_version":"1.0","message_id":mid,"from":"peer70","to":"peer136","type":"request","timeout":120,"payload":{"text":"Ciao peer136! peer70 chiede: controlla se nella tua memoria ci sono riferimenti al vecchio HMP v1 (porta 8643, hmp.py standalone). Se li trovi, cancellali. Tieni solo HMP v2 su 18643. Riporta cosa hai fatto."}})
    r = urlopen(f"http://{ip}:18643/hmp/send", data=body.encode(), timeout=10)
    print(f"Send: {r.read().decode().strip()[:100]}")
except Exception as e:
    print(f"Send failed: {type(e).__name__}: {e}")
print("=== Script done ===")
sys.exit(0)
