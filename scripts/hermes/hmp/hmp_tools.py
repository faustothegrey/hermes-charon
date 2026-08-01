#!/usr/bin/env python3
"""
hmp_tools.py — Wrapper Python per HMP operations.
Importabile da execute_code() per inviare e ricevere messaggi HMP
senza chiamare bash ogni volta.

Uso da execute_code:
  from hermes_tools import terminal
  exec(open('/home/fausto/.hermes/scripts/hmp/hmp_tools.py').read())
  
  # Send and wait (bloccante)
  resp = hmp_send_and_wait(105, "Ciao? Rispondi in max 2 frasi")
  print(resp)
  
  # Solo send
  msgid = hmp_send(106, "Test")
  
  # Poll
  resp = hmp_poll(106, msgid)
  
  # Broadcast
  results = hmp_broadcast("Annuncio!")
"""
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

HMP_PORT = 18643
HMP_FROM = "peer70"

def _hmp_url(peer_id: int, path: str) -> str:
    return f"http://192.168.178.{peer_id}:{HMP_PORT}{path}"

def _make_msgid(prefix: str, peer_id: int) -> str:
    return f"{prefix}_{peer_id}_{int(time.time()*1000000)}"

def hmp_send(peer_id: int, text: str, prefix: str = "msg") -> str:
    """Invia un messaggio HMP. Restituisce message_id o solleva eccezione."""
    msgid = _make_msgid(prefix, peer_id)
    payload = {
        "hmp_version": "1.0",
        "message_id": msgid,
        "idempotency_key": msgid,
        "from": HMP_FROM,
        "to": f"peer{peer_id}",
        "type": "request",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timeout": 120,
        "payload": {"text": text},
    }
    data = json.dumps(payload).encode()
    req = Request(_hmp_url(peer_id, "/hmp/send"), data=data,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except (HTTPError, URLError, OSError) as e:
        raise RuntimeError(f"HMP send to peer{peer_id} failed: {e}")

    if not result.get("accepted"):
        raise RuntimeError(f"HMP send rejected: {result.get('error', 'unknown')}")
    return msgid


def hmp_poll(peer_id: int, message_id: str) -> dict:
    """Poll singolo. Restituisce dict con status, response_text, ecc."""
    try:
        with urlopen(_hmp_url(peer_id, f"/hmp/poll/{message_id}"), timeout=5) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, OSError) as e:
        return {"status": "error", "error": str(e)}


def hmp_send_and_wait(peer_id: int, text: str, prefix: str = "msg",
                       max_polls: int = 30, poll_interval: float = 3.0) -> str:
    """Invia messaggio e poll fino a completed. Restituisce response_text."""
    msgid = hmp_send(peer_id, text, prefix)

    for i in range(max_polls):
        result = hmp_poll(peer_id, msgid)
        status = result.get("status")

        if status == "completed":
            return result.get("response_text", "") or ""
        elif status == "failed":
            raise RuntimeError(f"Peer{peer_id} failed: {result.get('error', 'unknown')}")
        elif status == "not_found":
            raise RuntimeError(f"Message {msgid} not found on peer{peer_id}")
        # else: still working, retry

        time.sleep(poll_interval)

    raise TimeoutError(f"Peer{peer_id} did not complete after {max_polls * poll_interval}s")


def hmp_broadcast(text: str, peers: list = None) -> dict:
    """Invia a tutti i peer. Restituisce {peer_id: messagge_id o errore}."""
    if peers is None:
        peers = [105, 106, 84, 128]
    results = {}
    for pid in peers:
        try:
            msgid = hmp_send(pid, text, "broadcast")
            results[pid] = {"status": "sent", "message_id": msgid}
        except RuntimeError as e:
            results[pid] = {"status": "error", "error": str(e)}
    return results


# ── Esempio d'uso se eseguito direttamente ────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 hmp_tools.py send <peer> <text>")
        print("  python3 hmp_tools.py poll <peer> <message_id>")
        print("  python3 hmp_tools.py sendwait <peer> <text>")
        print("  python3 hmp_tools.py broadcast <text>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "broadcast":
        text = sys.argv[2] if len(sys.argv) > 2 else "ping"
        results = hmp_broadcast(text)
        for pid, r in results.items():
            icon = "✅" if r["status"] == "sent" else "❌"
            print(f"  {icon} peer{pid}: {r.get('message_id', r.get('error', '?'))}")
        sys.exit(0)

    if len(sys.argv) < 3:
        print(f"Usage: python3 hmp_tools.py {cmd} <peer> ...")
        sys.exit(1)

    peer = int(sys.argv[2])

    if cmd == "send":
        text = sys.argv[3] if len(sys.argv) > 3 else "ping"
        msgid = hmp_send(peer, text)
        print(msgid)

    elif cmd == "poll":
        msgid = sys.argv[3]
        result = hmp_poll(peer, msgid)
        print(json.dumps(result, indent=2))

    elif cmd == "sendwait":
        text = sys.argv[3] if len(sys.argv) > 3 else "ping"
        resp = hmp_send_and_wait(peer, text)
        print(resp)
