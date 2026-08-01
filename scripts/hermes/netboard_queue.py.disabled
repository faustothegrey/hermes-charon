#!/usr/bin/env python3
"""
netboard_queue.py — Coda messaggi prioritaria per NetBoard.

Inviare un messaggio:
  python3 netboard_queue.py send "Ciao!" --priority 10 --duration 30 --sub "sottotitolo"
  
Leggere il messaggio attivo:
  python3 netboard_queue.py active

Pulire messaggi scaduti:
  python3 netboard_queue.py clean
"""
import json, os, time, uuid, sys, argparse, shutil

QUEUE_PATH = os.path.expanduser("~/.hermes/netboard_queue.json")
LOCK_PATH = QUEUE_PATH + ".lock"

def _lock():
    """Semaforo semplice con file lock."""
    for _ in range(10):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            return fd
        except FileExistsError:
            time.sleep(0.1)
    raise TimeoutError("Cannot acquire queue lock")

def _unlock(fd):
    os.close(fd)
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass

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

def cmd_send(text, priority=5, duration=30, subtitle=None):
    fd = _lock()
    try:
        queue = load_queue()
        msg = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "priority": priority,
            "duration": duration,
            "text": text,
            "subtitle": subtitle,
            "added_at": time.time(),
            "active_since": None,
        }
        queue.append(msg)
        save_queue(queue)
        print(f"✅ Messaggio accodato (ID: {msg['id']}, priorità {priority}, durata {duration}s)")
        return msg["id"]
    finally:
        _unlock(fd)

def cmd_active():
    """Restituisce il messaggio attivo (massima priorità non scaduto) oppure None."""
    fd = _lock()
    try:
        queue = load_queue()
        now = time.time()
        
        # Rimuovi scaduti
        active = [m for m in queue if m.get("active_since") is not None]
        expired = [m for m in active if (now - m["active_since"]) >= m["duration"]]
        pending = [m for m in queue if m.get("active_since") is None]
        
        for m in expired:
            print(f"  ⌛ Scaduto: {m.get('text', '?')} (ID: {m['id']})", file=sys.stderr)
        
        queue = [m for m in queue if m not in expired]
        
        # Trova il candidato: il pending con priorità più alta
        if pending:
            best = max(pending, key=lambda m: (m["priority"], -m["added_at"]))
            # Controlla se c'è già un attivo con priorità maggiore
            still_active = [m for m in active if m not in expired]
            if still_active:
                current = max(still_active, key=lambda m: m["priority"])
                if best["priority"] > current["priority"]:
                    # Preempt! Il corrente diventa pending
                    current["active_since"] = None
                    best["active_since"] = now
                    queue = [m for m in queue if m != current] + [current]
                    print(f"  ⚡ Preempt: {best.get('text','?')} (> {current.get('text','?')})", file=sys.stderr)
                elif best["priority"] == current["priority"]:
                    # Stessa priorità, finché il current è attivo lascia stare
                    pass
                else:
                    # Priorità minore, aspetta
                    pass
            else:
                best["active_since"] = now
                print(f"  ▶ Attivo: {best.get('text','?')}", file=sys.stderr)

            # Ricarica current dopo eventuali modifiche
            queue = [m for m in queue if m not in expired]
            active_now = [m for m in queue if m.get("active_since") is not None]
            if active_now:
                current = max(active_now, key=lambda m: m["priority"])
                save_queue(queue)
                return current
            else:
                # Promuovi il best
                best = max(pending, key=lambda m: (m["priority"], -m["added_at"]))
                best["active_since"] = now
                save_queue(queue)
                return best
        
        # Nessun pending, eventuali attivi residui
        if active:
            current = max(active, key=lambda m: m["priority"])
            save_queue(queue)
            return current
        
        save_queue(queue)
        return None
    finally:
        _unlock(fd)

def cmd_clean():
    fd = _lock()
    try:
        queue = load_queue()
        now = time.time()
        fresh = [
            m for m in queue
            if m.get("active_since") is None
            or (now - m["active_since"]) < m["duration"]
        ]
        removed = len(queue) - len(fresh)
        save_queue(fresh)
        print(f"✅ Puliti {removed} messaggi scaduti. {len(fresh)} in coda.")
    finally:
        _unlock(fd)

def cmd_list():
    queue = load_queue()
    now = time.time()
    if not queue:
        print("📭 Coda vuota")
        return
    print(f"{'ID':<20} {'Priorità':<10} {'Durata':<10} {'Testo':<30} {'Stato'}")
    print("-" * 80)
    for m in sorted(queue, key=lambda x: (-x.get("priority", 0), x.get("added_at", 0))):
        as_ = m.get("active_since")
        if as_ is None:
            stato = "⏳ in attesa"
        elif (now - as_) < m["duration"]:
            rimanenti = int(m["duration"] - (now - as_))
            stato = f"▶ attivo ({rimanenti}s rimaste)"
        else:
            stato = "⌛ scaduto"
        text = m.get("text", "?")[:28]
        print(f"{m['id']:<20} {m.get('priority',0):<10} {m.get('duration',0):<10} {text:<30} {stato}")

def main():
    parser = argparse.ArgumentParser(description="NetBoard message queue")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    p_send = sub.add_parser("send", help="Invia un messaggio")
    p_send.add_argument("text", help="Testo del messaggio")
    p_send.add_argument("--priority", "-p", type=int, default=5, help="Priorità 1-100 (default: 5)")
    p_send.add_argument("--duration", "-d", type=int, default=30, help="Durata in secondi (default: 30)")
    p_send.add_argument("--sub", "-s", default=None, help="Sottotitolo opzionale")
    
    sub.add_parser("active", help="Mostra il messaggio attivo")
    sub.add_parser("clean", help="Pulisci messaggi scaduti")
    sub.add_parser("list", help="Elenca tutti i messaggi in coda")
    
    args = parser.parse_args()
    
    if args.cmd == "send":
        cmd_send(args.text, args.priority, args.duration, args.sub)
    elif args.cmd == "active":
        msg = cmd_active()
        if msg:
            print(json.dumps(msg))
        else:
            print("null")
    elif args.cmd == "clean":
        cmd_clean()
    elif args.cmd == "list":
        cmd_list()

if __name__ == "__main__":
    main()
