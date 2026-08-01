#!/usr/bin/env python3
"""netboard-cli — mostra lo stato della rete in terminale.
Uso: netboard-cli [watch]   (senza arg: one-shot; con 'watch': aggiornamento ogni 5s)"""

import os
import sys
import time
import subprocess
import shutil

# ─── Config ───────────────────────────────────────────────────────────────────
PEERS = [
    ("🌐 FRITZ!Box",  "192.168.178.1",  "Router"),
    ("🖥  peer70",    "192.168.178.70",  "Orchestratore"),
    ("💻 peer84",     "192.168.178.84",  "N56VV"),
    ("🍏 peer128",    "192.168.178.128", "MacBook"),
    ("⏹  peer60",    "192.168.178.60",  "Inattivo"),
]

REFRESH = 5  # seconds for watch mode

# ─── ANSI ─────────────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
RESET  = "\033[0m"
GREEN  = "\033[38;2;60;200;100m"
RED    = "\033[38;2;220;60;60m"
YELLOW = "\033[38;2;220;200;40m"
GREY   = "\033[38;2;80;80;90m"
WHITE  = "\033[38;2;210;210;220m"
DIM    = "\033[38;2;120;120;140m"
CYAN   = "\033[38;2;70;130;200m"
BGY   = "\033[48;2;30;32;45m"
BG    = "\033[48;2;15;15;25m"

def ping(ip):
    try:
        start = time.monotonic()
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True, text=True, timeout=3
        )
        ms = (time.monotonic() - start) * 1000
        return r.returncode == 0, round(ms, 1)
    except Exception:
        return False, None

def render(peers_data):
    """Renderizza la tabella dello stato."""
    cols = shutil.get_terminal_size().columns

    lines = []
    lines.append(f"{BG}{CYAN}{BOLD}  📡 NetBoard — Stato Rete Locale{RESET}")
    lines.append(f"{BG}{DIM}  {'─' * (cols - 3)}{RESET}")
    lines.append("")

    for name, ip, desc, online, ms in peers_data:
        if online is None:
            dot = f"{GREY}⏳{RESET}"
            status = f"{GREY}scanning…{RESET}"
        elif online:
            dot = f"{GREEN}●{RESET}" if ms < 50 else f"{YELLOW}●{RESET}"
            status = f"{GREEN}{ms}ms{RESET}" if ms else f"{GREEN}online{RESET}"
        else:
            dot = f"{RED}✗{RESET}"
            status = f"{RED}offline{RESET}"

        line = f"  {dot}  {WHITE}{name:12s}{RESET}  {DIM}{ip:15s}{RESET}  {status:12s}  {DIM}{desc}{RESET}"
        lines.append(line)

    lines.append("")
    lines.append(f"{BG}{DIM}  Aggiornato: {time.strftime('%H:%M:%S')}  |  q per uscire{RESET}")

    return "\n".join(lines)

def main():
    watch_mode = len(sys.argv) > 1 and sys.argv[1] == "watch"

    try:
        while True:
            # Ping all peers
            results = []
            for name, ip, desc in PEERS:
                ok, ms = ping(ip)
                results.append((name, ip, desc, ok, ms))

            out = render(results)
            if watch_mode:
                # Clear screen and print
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(out)
                sys.stdout.flush()
                time.sleep(REFRESH)
            else:
                print(out)
                break

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
