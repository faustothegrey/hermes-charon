#!/usr/bin/env python3
"""send-when-online.py — deliver a message to a flaky/offline HMP peer when it comes back.

Pattern: peer was OK recently (hmp-healthcheck.log) but is DOWN now -> intermittent
(reboot, WiFi flapping), not dead. Poll /health, send via dual-plane :18644 when up,
exactly once (flag file guards against duplicate sends).

Usage:
  python3 send-when-online.py --peer 192.168.178.106 \
      --session peer106_peer70 --timeout 600 \
      --message "Hi peer106 — ..."

Options:
  --peer         peer IP (required)
  --session      dual-plane session_id (peer_pair_id, e.g. peer106_peer70)
  --message      text to send, or
  --message-file path to file containing the text
  --timeout      max seconds to wait for the peer (default 600)
  --health-port  health check port (default 18643)
  --send-port    dual-plane send port (default 18644)
  --flag         idempotency flag path (default /tmp/send-when-online-<session>.flag)

Stdlib only. Run in background (terminal background=true, notify_on_complete=true).
Keep message < 2048 chars (HMP max_text_length) and use a stable session_id.
"""
import argparse
import json
import os
import sys
import time
from urllib.request import Request, urlopen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--peer", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--message", default=None)
    ap.add_argument("--message-file", default=None)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--health-port", type=int, default=18643)
    ap.add_argument("--send-port", type=int, default=18644)
    ap.add_argument("--flag", default=None)
    a = ap.parse_args()

    if a.message is None:
        if a.message_file:
            a.message = open(a.message_file).read().strip()
        else:
            print("ERROR: --message or --message-file required")
            return 2

    flag = a.flag or f"/tmp/send-when-online-{a.session}.flag"
    if os.path.exists(flag):
        print(f"ALREADY SENT ({flag}) — exiting, no duplicate send")
        return 0

    health = f"http://{a.peer}:{a.health_port}/health"
    send = f"http://{a.peer}:{a.send_port}/send"

    def up():
        try:
            with urlopen(health, timeout=4) as r:
                return r.status == 200
        except Exception:
            return False

    deadline = time.time() + a.timeout
    while time.time() < deadline:
        if up():
            break
        time.sleep(20)
    else:
        print(f"peer {a.peer} still DOWN after {a.timeout}s — aborting, message not sent")
        return 1

    time.sleep(3)  # let the peer's HMP settle after boot
    body = json.dumps({"session_id": a.session, "text": a.message}).encode()
    try:
        req = Request(send, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
        print("SEND result:", json.dumps(resp)[:400])
        if resp.get("status") == "ok" or "response" in resp:
            with open(flag, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            print(f"DELIVERED — flag written ({flag})")
        else:
            print("WARNING: response without ok status, flag NOT written")
            return 2
    except Exception as e:
        print("SEND FAILED:", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
