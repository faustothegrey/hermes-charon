#!/usr/bin/env python3
"""
HMP Worker-Router — per peer worker (peer84, peer128)
Eseguito ogni 30s via cron.
1. Legge messaggi pending nel DB locale destinati a questo peer
2. Li marca: pending -> delivered -> working
3. Processa il task (ping/query/general)
4. Invia risposta via HMP al mittente
5. Marca: completed

Zero dipendenze esterne (solo stdlib).
"""
import json
import os
import time
import sqlite3
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# --- Config ---
PEER_NAME = os.environ.get("HMP_PEER_NAME", "peer84")
HMP_COORDINATOR = "http://192.168.178.70:8643"

# Auto-detect DB path per platform
_HOME = os.path.expanduser("~")
if os.path.exists(os.path.join(_HOME, ".hermes/data/hmp/agent_messages.db")):
    DB_PATH = os.path.join(_HOME, ".hermes/data/hmp/agent_messages.db")
elif os.path.exists("/root/.hermes/data/hmp/agent_messages.db"):
    DB_PATH = "/root/.hermes/data/hmp/agent_messages.db"
    PEER_NAME = "peer84"
elif os.path.exists("/Users/fausto/.hermes/data/hmp/agent_messages.db"):
    DB_PATH = "/Users/fausto/.hermes/data/hmp/agent_messages.db"
    PEER_NAME = "peer128"
else:
    DB_PATH = os.path.join(_HOME, ".hermes/data/hmp/agent_messages.db")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def send_via_hmp(to_peer, payload, in_reply_to=None):
    """Send a response back to coordinator via HMP POST /hmp/send."""
    resp_id = f"resp_{PEER_NAME}_{int(time.time())}"
    msg = {
        "hmp_version": "1.0",
        "message_id": resp_id,
        "idempotency_key": resp_id,
        "from": PEER_NAME,
        "to": to_peer,
        "type": "response",
        "timestamp": now_iso(),
        "timeout": 30,
        "payload": payload,
    }
    if in_reply_to:
        msg["in_reply_to"] = in_reply_to

    data = json.dumps(msg).encode()
    req = Request(
        f"{HMP_COORDINATOR}/hmp/send",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError) as ex:
        return {"error": str(ex)}


def process_payload(msg):
    """Build response payload from a message."""
    p = msg.get("payload", {})
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            p = {"raw": p}

    task_type = p.get("task_type", "general") if isinstance(p, dict) else "general"

    if task_type == "ping":
        return {
            "answer": f"Pong da {PEER_NAME}!",
            "status": "online",
            "hostname": PEER_NAME,
        }
    return {
        "answer": f"{PEER_NAME}: ricevuto e processato",
        "status": "ok",
    }


def main():
    if not os.path.exists(DB_PATH):
        print(f"hmp-worker({PEER_NAME}): DB non trovato: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    processed = 0

    # Trova messaggi pending destinati a questo peer
    pending = conn.execute(
        "SELECT * FROM messages WHERE to_peer = ? AND status = 'pending' ORDER BY created_at ASC LIMIT 10",
        (PEER_NAME,),
    ).fetchall()

    for row in pending:
        msg = dict(row)
        mid = msg["message_id"]

        # pending -> delivered -> working
        conn.execute(
            "UPDATE messages SET status='delivered', delivered_at=? WHERE message_id=?",
            (now_iso(), mid),
        )
        conn.commit()
        conn.execute(
            "UPDATE messages SET status='working', updated_at=? WHERE message_id=?",
            (now_iso(), mid),
        )
        conn.commit()

        # Processa e invia risposta
        response_payload = process_payload(msg)
        result = send_via_hmp(
            msg["from_peer"], response_payload, in_reply_to=mid
        )

        if "duplicate" in result or "message_id" in result:
            conn.execute(
                "UPDATE messages SET status='completed', completed_at=? WHERE message_id=?",
                (now_iso(), mid),
            )
            conn.commit()
            print(f"  OK {mid}: risposto a {msg['from_peer']}")
            processed += 1
        else:
            conn.execute(
                "UPDATE messages SET status='failed', error=? WHERE message_id=?",
                (json.dumps(result), mid),
            )
            conn.commit()
            print(f"  FAIL {mid}: {result}")

    conn.close()

    if processed == 0:
        print(f"hmp-worker({PEER_NAME}): idle")
    else:
        print(f"hmp-worker({PEER_NAME}): {processed} messaggi processati")


if __name__ == "__main__":
    main()