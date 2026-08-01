#!/usr/bin/env python3
import json, urllib.request, sys, os, sqlite3

results = []

# Test 1: Health check on :18644
try:
    r = urllib.request.urlopen("http://127.0.0.1:18644/health", timeout=5)
    health = json.loads(r.read())
    results.append(f"HEALTH: OK - {json.dumps(health)}")
except Exception as e:
    results.append(f"HEALTH: FAIL - {e}")

# Test 2: Send via dual-plane :18644/send
body = json.dumps({
    "session_id": "peer70_peer106",
    "text": "Test server-side v2. Rispondi solo OK se funziona.",
    "max_tokens": 256
}).encode()
try:
    req = urllib.request.Request(
        "http://127.0.0.1:18644/send",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    r = urllib.request.urlopen(req, timeout=60)
    result = json.loads(r.read())
    results.append(f"SEND: {json.dumps(result, indent=2)}")
except Exception as e:
    results.append(f"SEND: FAIL - {e}")

# Test 3: Check if dual-plane DB was created
db = os.path.expanduser("~/.hermes/data/hmp/dual-plane.db")
if os.path.isfile(db):
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT * FROM sessions").fetchall()
    results.append(f"DB sessions: {rows}")
    conn.close()
else:
    results.append("DB: not found")

# Test 4: Quick HMP health to verify gateway is up
try:
    r = urllib.request.urlopen("http://127.0.0.1:18643/health", timeout=5)
    hmp_health = json.loads(r.read())
    results.append(f"HMP HEALTH: {json.dumps(hmp_health)}")
except Exception as e:
    results.append(f"HMP HEALTH: FAIL - {e}")

print("=== Dual-Plane v2 Test Results ===")
print("\n".join(results))
print("=== END ===")
sys.exit(0)
