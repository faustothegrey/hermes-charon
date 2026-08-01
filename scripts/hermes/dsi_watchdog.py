#!/usr/bin/env python3
"""
dsi_watchdog.py — Monitora dmesg per errori del bridge DSI.

Se rileva un errore tc358762/DSI timeout, notifica su Telegram.
Cron consigliato: ogni 5 minuti, no_agent=true.
"""
import subprocess
import sys
import os
import json
from datetime import datetime

STATE_FILE = os.path.expanduser("~/.hermes/dsi_watchdog_state.json")
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

def log(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_error_ts": 0, "last_notified_ts": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def check_dmesg():
    result = subprocess.run(
        ["sudo", "dmesg"],
        capture_output=True, text=True, timeout=10
    )
    errors = []
    now = datetime.now().timestamp()
    for line in result.stdout.split('\n'):
        if "DSI transfer failed" in line or "transfer interrupt wait timeout" in line:
            errors.append(line)
        if "tc358762" in line and ("error" in line or "fail" in line):
            errors.append(line)
    return errors

def main():
    errors = check_dmesg()
    if not errors:
        log("dsi_watchdog: nessun errore DSI")
        return

    state = load_state()
    now = datetime.now().timestamp()
    last_error_line = errors[-1]

    # Estrai timestamp dmesg se possibile
    try:
        dmesg_secs = float(last_error_line.split(']')[0].strip('['))
        log(f"dsi_watchdog: errore DSI rilevato a +{dmesg_secs:.0f}s dal boot")
    except (ValueError, IndexError):
        dmesg_secs = now

    # Notifica solo se è un errore nuovo (non già notificato nelle ultime 6h)
    if dmesg_secs > state.get("last_error_ts", 0) + 10:
        state["last_error_ts"] = dmesg_secs

        # Mostra su display NetBoard
        try:
            subprocess.run(
                ["netboard-msg", "⚠️ Errore DSI bridge! Corri dsi-recover",
                 "--priority", "90", "--duration", "20",
                 "--sub", "Display potrebbe spegnersi"],
                timeout=5, capture_output=True
            )
        except Exception:
            pass

        print(f"⚠️ DSI ERROR: {last_error_line[:100]}")

        # Se non abbiamo notificato nelle ultime 12h, manda su Telegram
        if now - state.get("last_notified_ts", 0) > 43200:
            state["last_notified_ts"] = now
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"▶️ Notifica Telegram: DSI bridge error")

        save_state(state)
    else:
        log("dsi_watchdog: errore già notificato")

if __name__ == "__main__":
    main()
