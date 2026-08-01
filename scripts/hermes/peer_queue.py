#!/usr/bin/env python3
"""
peer_queue.py — Coda messaggi per peer HMP.

Inviare un messaggio:
  python3 peer_queue.py send peer84 "Ciao!" [--priority 5]

Inviare a più peer:
  python3 peer_queue.py send peer84,peer105 "Ciao a tutti!"

Lista messaggi:
  python3 peer_queue.py list [peer84]

Stato peer:
  python3 peer_queue.py status

Recapito immediato (tenta tutti i pending):
  python3 peer_queue.py deliver

Cron consigliato: peer_queue.py deliver ogni 2-5 minuti.

La coda è in ~/.hermes/peer_queue.json, con lock file.
"""
import json
import os
import sys
import time
import uuid
import argparse
import urllib.request
import urllib.error
import subprocess

# ─── Config ───────────────────────────────────────────────────────────────────
QUEUE_PATH = os.path.expanduser("~/.hermes/peer_queue.json")
LOCK_PATH = QUEUE_PATH + ".lock"
HMP_PORT = 18643
MAX_ATTEMPTS = 10
RETRY_DELAY = 120  # secondi tra tentativi (sovrascritto dal cron 2min)

# Peer registry: name -> IP
PEER_IP = {
    "peer70":  "192.168.178.70",
    "peer84":  "192.168.178.84",
    "peer105": "192.168.178.105",
    "peer106": "192.168.178.106",
    "peer128": "192.168.178.112",
    "peer58":  "192.168.178.58",
    "peer136": "192.168.178.136",
}

PEER_LABEL = {
    "peer70":  "Charon (questo)",
    "peer84":  "N56VV",
    "peer105": "Fedora30",
    "peer106": "Fedora30 ARM",
    "peer128": "MacBook",
    "peer58":  "HMP peer",
    "peer136": "Trixie",
}


# ─── Lock ──────────────────────────────────────────────────────────────────────
def _lock():
    for _ in range(15):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return fd
        except FileExistsError:
            time.sleep(0.1)
    raise TimeoutError("Cannot acquire peer queue lock")


def _unlock(fd):
    os.close(fd)
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass


# ─── Queue IO ──────────────────────────────────────────────────────────────────
def load_queue():
    try:
        with open(QUEUE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_queue(queue):
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, 'w') as f:
        json.dump(queue, f, indent=2)


# ─── Health Check ──────────────────────────────────────────────────────────────
def peer_health(peer_name):
    """Return True if peer's HMP gateway responds to /health."""
    ip = PEER_IP.get(peer_name)
    if not ip:
        return False
    try:
        req = urllib.request.Request(f"http://{ip}:{HMP_PORT}/health")
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
            return data.get("status") == "ok"
    except Exception:
        return False


# ─── HMP Send ──────────────────────────────────────────────────────────────────
def hmp_send(peer_name, text, from_name="peer70"):
    """Send a text message to a peer via HMP. Returns True on success."""
    ip = PEER_IP.get(peer_name)
    if not ip:
        return False

    msgid = f"peerq_{uuid.uuid4().hex[:12]}"
    payload = json.dumps({
        "hmp_version": "1.0",
        "message_id": msgid,
        "from": from_name,
        "to": peer_name,
        "type": "request",
        "timeout": 60,
        "payload": {"text": text}
    }).encode()

    try:
        req = urllib.request.Request(
            f"http://{ip}:{HMP_PORT}/hmp/send",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
        return result.get("accepted", False)
    except Exception:
        return False


# ─── Commands ──────────────────────────────────────────────────────────────────
def cmd_send(peer_names, text, priority=5, from_name="peer70"):
    """Accoda un messaggio per uno o più peer."""
    peers = [p.strip() for p in peer_names.split(",")]
    unknown = [p for p in peers if p not in PEER_IP]
    if unknown:
        print(f"❌ Peer sconosciuti: {', '.join(unknown)}")
        print(f"   Conosciuti: {', '.join(sorted(PEER_IP.keys()))}")
        return

    fd = _lock()
    try:
        queue = load_queue()
        for peer in peers:
            msg = {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "to": peer,
                "text": text,
                "priority": priority,
                "from": from_name,
                "status": "pending",
                "attempts": 0,
                "max_attempts": MAX_ATTEMPTS,
                "created_at": time.time(),
                "delivered_at": None,
                "last_attempt": None,
                "last_error": None,
            }
            queue.append(msg)
            print(f"  📥 Accodato per {peer}: '{text}' (priorità {priority})")
        save_queue(queue)
    finally:
        _unlock(fd)


def cmd_list(filter_peer=None):
    """Mostra i messaggi in coda."""
    queue = load_queue()
    if filter_peer and filter_peer not in PEER_IP:
        print(f"❌ Peer sconosciuto: {filter_peer}")
        return

    pending = [m for m in queue if m["status"] == "pending"]
    delivered = [m for m in queue if m["status"] == "delivered"]
    failed = [m for m in queue if m["status"] == "failed"]

    if filter_peer:
        pending = [m for m in pending if m["to"] == filter_peer]
        delivered = [m for m in delivered if m["to"] == filter_peer]
        failed = [m for m in failed if m["to"] == filter_peer]

    if not any([pending, delivered, failed]):
        print("📭 Nessun messaggio in coda")
        return

    if pending:
        print(f"\n⏳ Pending ({len(pending)}):")
        for m in sorted(pending, key=lambda x: (-x["priority"], x["created_at"])):
            age = int(time.time() - m["created_at"])
            peer_label = PEER_LABEL.get(m["to"], m["to"])
            print(f"  [{m['id'][:8]}] → {m['to']} ({peer_label}) | "
                  f"priorità {m['priority']} | tentativi {m['attempts']} | "
                  f"{age}s fa")
            elip = "…" if len(m['text']) > 60 else ""
            print(f'         "{m["text"][:60]}{elip}"')

    if delivered:
        print(f"\n✅ Consegnati (ultimi {min(3, len(delivered))}):")
        for m in sorted(delivered, key=lambda x: -x.get("delivered_at", 0))[:3]:
            peer_label = PEER_LABEL.get(m["to"], m["to"])
            eta = int(time.time() - (m.get("delivered_at") or m["created_at"]))
            print(f"  [{m['id'][:8]}] → {m['to']} ({peer_label}) | {eta}s fa")
            elip = "…" if len(m['text']) > 60 else ""
            print(f'         "{m["text"][:60]}{elip}"')

    if failed:
        print(f"\n❌ Falliti ({len(failed)}):")
        for m in sorted(failed, key=lambda x: -x["created_at"])[:3]:
            peer_label = PEER_LABEL.get(m["to"], m["to"])
            print(f"  [{m['id'][:8]}] → {m['to']} ({peer_label}) | "
                  f"{m['attempts']} tentativi | errore: {m.get('last_error','?')}")
            elip = "…" if len(m['text']) > 60 else ""
            print(f'         "{m["text"][:60]}{elip}"')


def cmd_status():
    """Mostra lo stato online/offline di tutti i peer."""
    print("🌐 Stato peer HMP:\n")
    for name in sorted(PEER_IP.keys()):
        if name == "peer70":
            print(f"  ● {name:8} {PEER_IP[name]:15} {PEER_LABEL.get(name,''):20} ← locale")
            continue
        online = peer_health(name)
        icon = "🟢" if online else "🔴"
        label = PEER_LABEL.get(name, "")
        print(f"  {icon} {name:8} {PEER_IP[name]:15} {label} "
              f"{'(online)' if online else '(offline)'}")


def cmd_deliver():
    """Tenta di consegnare tutti i messaggi in sospeso."""
    queue = load_queue()
    pending = [m for m in queue if m["status"] == "pending"]

    if not pending:
        print("peer-queue: nessun messaggio pending")
        return

    delivered_count = 0
    failed_count = 0

    for msg in pending:
        peer = msg["to"]
        now = time.time()

        # Salta se ritardo minimo non trascorso
        if msg.get("last_attempt"):
            elapsed = now - msg["last_attempt"]
            if elapsed < RETRY_DELAY:
                continue

        # Health check
        if not peer_health(peer):
            msg["last_attempt"] = now
            msg["attempts"] += 1
            msg["last_error"] = "offline"
            failed_count += 1
            continue

        # Invia
        success = hmp_send(peer, msg["text"], msg.get("from", "peer70"))

        if success:
            msg["status"] = "delivered"
            msg["delivered_at"] = now
            msg["last_attempt"] = now
            delivered_count += 1
            print(f"  ✅ {peer}: \"{msg['text'][:50]}\"")
        else:
            msg["last_attempt"] = now
            msg["attempts"] += 1
            msg["last_error"] = "send_failed"
            failed_count += 1
            if msg["attempts"] >= msg["max_attempts"]:
                msg["status"] = "failed"
                print(f"  ❌ {peer}: superati {msg['max_attempts']} tentativi")
            else:
                print(f"  ⏳ {peer}: tentativo {msg['attempts']}/{msg['max_attempts']} fallito")

    save_queue(queue)

    if delivered_count > 0:
        # Notifica sul display NetBoard
        peers_delivered = [m["to"] for m in pending if m["status"] == "delivered"]
        if peers_delivered:
            peer_list = ", ".join(sorted(set(peers_delivered)))
            try:
                subprocess.run(
                    ["netboard-msg", f"📨 Messaggio recapitato a {peer_list}",
                     "--priority", "60", "--duration", "10",
                     "--sub", "Peer-queue delivery"],
                    timeout=5, capture_output=True
                )
            except Exception:
                pass

    total = len(pending)
    print(f"peer-queue: {delivered_count} consegnati, "
          f"{failed_count} falliti/ritentati su {total} pendenti")


def cmd_clean(older_than_hours=24):
    """Rimuove messaggi consegnati/falliti più vecchi di N ore."""
    queue = load_queue()
    now = time.time()
    cutoff = now - older_than_hours * 3600

    before = len(queue)
    queue = [m for m in queue if
             m["status"] == "pending" or
             (m.get("delivered_at") or m.get("last_attempt") or m["created_at"]) > cutoff]

    removed = before - len(queue)
    save_queue(queue)
    print(f"🧹 Puliti {removed} messaggi vecchi, {len(queue)} rimasti in coda")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Coda messaggi peer HMP")
    sub = parser.add_subparsers(dest="command", required=True)

    # send
    p_send = sub.add_parser("send", help="Accoda un messaggio")
    p_send.add_argument("peers", help="Peer destinatari (es. peer84 o peer84,peer105)")
    p_send.add_argument("text", help="Testo del messaggio")
    p_send.add_argument("--priority", type=int, default=5, help="Priorità (1-100)")
    p_send.add_argument("--from", dest="from_name", default="peer70", help="Mittente")

    # list
    p_list = sub.add_parser("list", help="Mostra messaggi in coda")
    p_list.add_argument("peer", nargs="?", help="Filtra per peer")

    # status
    sub.add_parser("status", help="Stato online/offline peer")

    # deliver
    p_deliver = sub.add_parser("deliver", help="Tenta consegna immediata")
    p_deliver.add_argument("--no-cooldown", action="store_true",
                           help="Ignora il ritardo minimo tra tentativi")

    # clean
    p_clean = sub.add_parser("clean", help="Pulisci messaggi vecchi")
    p_clean.add_argument("--hours", type=int, default=24, help="Ore di anzianità")

    args = parser.parse_args()

    if args.command == "send":
        cmd_send(args.peers, args.text, args.priority, args.from_name)
    elif args.command == "list":
        cmd_list(args.peer)
    elif args.command == "status":
        cmd_status()
    elif args.command == "deliver":
        if args.no_cooldown:
            global RETRY_DELAY
            RETRY_DELAY = 0
        cmd_deliver()
    elif args.command == "clean":
        cmd_clean(args.hours)


if __name__ == "__main__":
    main()
