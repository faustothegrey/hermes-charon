#!/usr/bin/env python3
"""
HMP Message Router v2 — cron script (no_agent=True)
Runs every 30s on peer70.

Extended with peer forwarding:
- to_peer=peer70  → pending → queued → delivered (DB locale, come prima)
- to_peer=peer84  → pending → queued → POST peer84:8642/v1/runs → delivered
- to_peer=peer128 → pending → queued → POST peer128:8642/v1/runs → delivered
"""
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

sys.path.insert(0, os.path.expanduser("~/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts"))

from hmp import init_cron, STATE_PENDING, STATE_QUEUED, STATE_DELIVERED, STATE_FAILED, new_message_id, now_iso

# ── Peer registry: API keys and endpoints ──
PEER_API = {
    "peer84": {
        "url": "http://192.168.178.84:8642/v1/runs",
        "key": "6j-h7Q5pR70Y2OXPVwtn-Mlv5DZItxu8d_tbwUYPD5uo5rf6G5E5aqQKdraydn2a",
        "timeout": 10,
    },
    "peer128": {
        "url": "http://192.168.178.112:8642/v1/runs",
        "key": "05d08de2c480511c1b6c775d5bbfac7063157b9bfccc07791da017f621975263",
        "timeout": 5,
    },
}


def forward_to_peer(msg, peer_name, peer_info):
    """Forward an HMP message to a peer via Hermes API /v1/runs."""
    payload = msg.get("payload", {})
    instruction = payload.get("instruction", "") if isinstance(payload, dict) else str(payload)

    body = json.dumps({
        "input": (
            f"[HMP message from {msg['from_peer']}]\n"
            f"Message ID: {msg['message_id']}\n"
            f"Task type: {payload.get('task_type', 'general')}\n\n"
            f"{instruction}\n\n"
            f"--\n"
            f"After processing, send your response back to peer70 via HMP:\n"
            f"POST http://192.168.178.70:8643/hmp/send\n"
            f'with type="response", in_reply_to="{msg["message_id"]}", '
            f'from="{peer_name}", to="peer70", and your answer in payload.\n'
            f"The hmp.py library has HMPClient().send_message() helper."
        )
    }).encode()

    req = Request(
        peer_info["url"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {peer_info['key']}",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=peer_info.get("timeout", 10)) as resp:
            result = json.loads(resp.read())
            run_id = result.get("id", result.get("run_id", "unknown"))
            print(f"  → Forwarded {msg['message_id']} to {peer_name}, run_id={run_id}")
            return True, run_id
    except HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  ❌ HTTP {e.code} forwarding to {peer_name}: {body}")
        return False, str(e)
    except URLError as e:
        print(f"  ❌ Network error forwarding to {peer_name}: {e.reason}")
        return False, str(e.reason)


def main():
    bus, config = load_config = init_cron()
    peer_name = config.get("peer_name", "peer70")

    # Step 1: pending → queued (take ownership of ALL messages)
    pending = bus._conn.execute(
        "SELECT * FROM messages WHERE status = ? ORDER BY created_at ASC LIMIT 50",
        (STATE_PENDING,)
    ).fetchall()

    for row in pending:
        msg = dict(row)
        for jf in ["payload", "error", "stats", "routing_path"]:
            if msg.get(jf) and isinstance(msg[jf], str):
                try:
                    msg[jf] = json.loads(msg[jf])
                except (json.JSONDecodeError, TypeError):
                    pass

        bus.update_status(msg["message_id"], STATE_QUEUED)

    # Step 2: queued → delivered (or forwarded)
    queued = bus._conn.execute(
        "SELECT * FROM messages WHERE status = ? ORDER BY created_at ASC LIMIT 50",
        (STATE_QUEUED,)
    ).fetchall()

    forwarded_count = 0
    local_count = 0
    failed_count = 0

    for row in queued:
        msg = dict(row)
        for jf in ["payload", "error", "stats", "routing_path"]:
            if msg.get(jf) and isinstance(msg[jf], str):
                try:
                    msg[jf] = json.loads(msg[jf])
                except (json.JSONDecodeError, TypeError):
                    pass

        target = msg.get("to_peer", "")

        if target == peer_name:
            # Local delivery
            bus.update_status(msg["message_id"], STATE_DELIVERED)
            local_count += 1
            print(f"  📥 {msg['message_id']}: → delivered (local)")

        elif target in PEER_API:
            # Remote delivery via API
            ok, result = forward_to_peer(msg, target, PEER_API[target])
            if ok:
                bus.update_status(msg["message_id"], STATE_DELIVERED,
                    stats={"forwarded_to": target, "run_id": result})
                forwarded_count += 1
                print(f"  📤 {msg['message_id']}: → delivered (→ {target})")
            else:
                bus.update_status(msg["message_id"], STATE_FAILED,
                    error={"code": "forward_failed", "message": str(result)})
                failed_count += 1
                print(f"  ❌ {msg['message_id']}: → failed (→ {target}): {result}")
        else:
            # Unknown peer
            bus.update_status(msg["message_id"], STATE_FAILED,
                error={"code": "unknown_peer", "message": f"No route to peer: {target}"})
            failed_count += 1
            print(f"  ❌ {msg['message_id']}: → failed (unknown peer: {target})")

    # Summary
    total = len(pending) + len(queued)
    if total > 0:
        print(f"hmp-message-router: {len(pending)} queued, {local_count} local, {forwarded_count} forwarded, {failed_count} failed")
    else:
        print("hmp-message-router: idle")

    bus.close()


if __name__ == "__main__":
    main()
