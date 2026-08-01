#!/usr/bin/env python3
"""Test dual-plane v2 /send endpoint."""
import json, urllib.request, sys, os

def test_send():
    payload = json.dumps({
        "session_id": "test_v2_001",
        "text": "Test server-side v2. Rispondi solo OK."
    }).encode()

    req = urllib.request.Request(
        "http://127.0.0.1:18644/send",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            print("SEND OK:", json.dumps(result, indent=2))
            return result
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
    except Exception as e:
        print(f"ERROR: {e}")

def test_health():
    try:
        with urllib.request.urlopen("http://127.0.0.1:18644/health", timeout=5) as r:
            print("HEALTH:", r.read().decode())
    except Exception as e:
        print(f"HEALTH ERROR: {e}")

if __name__ == "__main__":
    print("=== Dual-Plane v2 Test ===")
    test_health()
    print("---")
    test_send()
    sys.exit(0)
