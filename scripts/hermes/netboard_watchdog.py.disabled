#!/usr/bin/env python3
"""
netboard_watchdog.py — Controlla errori di netboard.service e li mostra sul display.

Uso: python3 netboard_watchdog.py [--minutes 10]
Cron consigliato: ogni 5 minuti.

Cerca nel journal gli errori dell'ultimo intervallo e se li trova:
1. Mostra un avviso sul display via netboard-msg
2. Salva l'evento in ~/.hermes/netboard_errors.log
"""
import subprocess
import sys
import os
import time
from datetime import datetime

def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
    sys.stderr.flush()

def main():
    minutes = 10
    if len(sys.argv) > 1 and sys.argv[1] == '--minutes':
        try:
            minutes = int(sys.argv[2])
        except (IndexError, ValueError):
            pass

    # Cerca nel journal le righe con "ERRORE" nel corpo
    since_str = f"{minutes} min ago"
    try:
        result = subprocess.run(
            ["journalctl", "-u", "netboard.service", "--since", since_str,
             "--no-pager", "--output", "short-iso"],
            capture_output=True, text=True, timeout=15
        )
    except subprocess.TimeoutExpired:
        log("watchdog: timeout reading journal")
        return
    except FileNotFoundError:
        log("watchdog: journalctl non trovato")
        return

    # Filtra solo le righe con ERRORE o Traceback
    error_lines = []
    for line in result.stdout.split('\n'):
        if 'ERRORE' in line or 'Traceback' in line or 'Error' in line:
            error_lines.append(line.strip())

    # Controlla anche l'exit code
    if result.returncode != 0 and result.returncode != 1:
        # journalctl returns 1 when no entries match
        log(f"watchdog: journalctl exit code {result.returncode}")

    if not error_lines:
        # Nessun errore — silenzioso
        log(f"watchdog: nessun errore negli ultimi {minutes} min")
        return

    # Conta errori distinti
    error_count = len(error_lines)
    first_error = error_lines[0]

    # Logga su file
    log_file = os.path.expanduser("~/.hermes/netboard_errors.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a') as f:
        f.write(f"\n=== {ts} ===\n")
        for line in error_lines:
            f.write(f"  {line}\n")

    # Mostra sul display
    msg = f"⚠️ {error_count} errore(i) netboard"
    subtitle = f"Vedi: journalctl -u netboard.service --since 1h"

    try:
        subprocess.run(
            ["netboard-msg", msg, "--priority", "80", "--duration", "15", "--sub", subtitle],
            timeout=5
        )
        log(f"watchdog: {error_count} errore(i) mostrati sul display")
    except Exception as e:
        log(f"watchdog: impossibile mostrare su display: {e}")

if __name__ == "__main__":
    main()
