#!/bin/bash
# ══════════════════════════════════════════════════════════════
# HMP Watchdog — peer70
# Controlla messaggi HMP bloccati in "working" più vecchi di 3 min
# LOGGA SOLO + avvisa peer70 via HMP (nessun auto-fail distruttivo)
# ══════════════════════════════════════════════════════════════

DB="/home/fausto/.hermes/data/hmp_gateway_plugin/messages.db"
LOG="/home/fausto/.hermes/logs/hmp-watchdog.log"
ALERT_FILE="/home/fausto/.hermes/logs/hmp-watchdog-alert.json"
THRESHOLD_MINUTES=3

mkdir -p "$(dirname "$LOG")"

python3 - "$DB" "$LOG" "$ALERT_FILE" "$THRESHOLD_MINUTES" <<'PYEOF'
import sqlite3, json, sys, time, os, urllib.request

DB_PATH = sys.argv[1]
LOG_PATH = sys.argv[2]
ALERT_PATH = sys.argv[3]
THRESHOLD_MIN = int(sys.argv[4])
NOW = time.time()
MAX_AGE = THRESHOLD_MIN * 60

if not os.path.exists(DB_PATH):
    exit(0)

try:
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    c.execute("""
        SELECT message_id, from_peer, to_peer, text, accepted_at
        FROM hmp_gateway_messages
        WHERE status = 'working'
          AND from_peer != 'watchdog'
          AND (? - accepted_at) > ?
        ORDER BY accepted_at
    """, (NOW, MAX_AGE))

    stuck = c.fetchall()
    db.close()

    if not stuck:
        # Nessun blocco: cancella alert precedente se esiste
        if os.path.exists(ALERT_PATH):
            os.remove(ALERT_PATH)
        exit(0)

    # Ci sono blocchi: logga e invia alert HMP a se stesso
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, 'a') as log:
        log.write("[%s] ⚠️ %d messaggio/i bloccato/i in working\n" % (ts, len(stuck)))
        alert_messages = []
        for msg in stuck:
            msg_id, from_peer, to_peer, text, accepted_at = msg
            stuck_secs = int(NOW - accepted_at)
            stuck_min = stuck_secs // 60
            log.write("  %s | %s->%s | bloccato %d min\n" % (msg_id, from_peer, to_peer, stuck_min))
            alert_messages.append({"message_id": msg_id, "from": from_peer, "stuck_seconds": stuck_secs})
            print("[watchdog] ⚠️ %s da %s bloccato %d min" % (msg_id, from_peer, stuck_min))

        # Salva alert JSON per consultazione rapida
        alert_data = {
            "timestamp": ts,
            "count": len(stuck),
            "messages": alert_messages
        }
        with open(ALERT_PATH, 'w') as f:
            json.dump(alert_data, f, indent=2)

        # Invia alert a me stesso via HMP
        peer_list = ", ".join([m["from"] for m in alert_messages[:5]])
        if len(alert_messages) > 5:
            peer_list += " e altri %d" % (len(alert_messages) - 5)
        alert_text = "⚠️ Watchdog: %d messaggio/i HMP bloccato/i in 'working' da >%d min. Da: %s. Controlla con: cat %s" % (
            len(stuck), THRESHOLD_MIN, peer_list, ALERT_PATH)

        alert_msg = json.dumps({
            "hmp_version": "1.0",
            "message_id": "watchdog_alert_%d" % int(NOW),
            "from": "watchdog",
            "to": "peer70",
            "type": "request",
            "timeout": 30,
            "payload": {"text": alert_text}
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                "http://127.0.0.1:18643/hmp/send",
                data=alert_msg,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("accepted") or result.get("status") == "accepted":
                log.write("[%s] ✅ Alert HMP inviato a peer70\n" % ts)
                print("[watchdog] ✅ Alert inviato a peer70")
            else:
                log.write("[%s] ❌ Alert HMP non accettato: %s\n" % (ts, result))
        except Exception as e:
            log.write("[%s] ❌ Errore invio alert HMP: %s\n" % (ts, e))
            print("[watchdog] ❌ Errore alert: %s" % e)

except Exception as e:
    with open(LOG_PATH, 'a') as log:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        log.write("[%s] ❌ ERRORE watchdog: %s\n" % (ts, e))
    print("[watchdog] ERROR: %s" % e)
PYEOF
