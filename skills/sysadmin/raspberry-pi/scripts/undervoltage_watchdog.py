#!/usr/bin/env python3
"""Undervoltage watchdog for Raspberry Pi.

Silent-unless-triggered cron script: prints ONLY when the under-voltage NOW bit
(bit 0 of `vcgencmd get_throttled`) is active AND the cooldown has elapsed.
Empty stdout = silence (cron no_agent jobs deliver nothing on empty stdout).

Pattern: read throttled -> latch last-alert timestamp to JSON state file ->
print a human alert with volts/temp/24h event count.

Usage: cron no_agent=true, schedule="every 15m", deliver=origin.
Cooldown: at most 1 alert per COOLDOWN_MIN if the problem persists; a new
episode after a return to normal alerts immediately.

Python 3.9 compatible (RPi OS Bullseye): no `int | None` syntax, use
`Optional[int]` from typing.
"""
import json
import os
import re
import subprocess
import time
from typing import Optional

STATE_FILE = os.path.expanduser("~/.hermes/state/undervoltage_state.json")
COOLDOWN_MIN = 60
HOST = os.uname().nodename


def _cmd(arg: str) -> str:
    try:
        out = subprocess.run(
            ["vcgencmd", arg], capture_output=True, text=True, timeout=10
        ).stdout
        return (out or "").strip()
    except Exception:
        return ""


def get_throttled() -> Optional[int]:
    out = _cmd("get_throttled")
    m = re.search(r"throttled=(0x[0-9a-fA-F]+)", out)
    return int(m.group(1), 16) if m else None


def measure_volts() -> str:
    m = re.search(r"volt=([\d.]+)V", _cmd("measure_volts"))
    return m.group(1) if m else "?"


def measure_temp() -> str:
    m = re.search(r"temp=([\d.]+)'C", _cmd("measure_temp"))
    return m.group(1) if m else "?"


def dmesg_events_last_hours(hours: int = 24) -> int:
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10).stdout
        boot_ts = time.time() - float(open("/proc/uptime").read().split()[0])
        count = 0
        for line in out.splitlines():
            if "Undervoltage" not in line:
                continue
            try:
                secs = float(line.split("]")[0].strip("["))
                if time.time() - (boot_ts + secs) < hours * 3600:
                    count += 1
            except ValueError:
                pass
        return count
    except Exception:
        return -1


def main() -> None:
    throttled = get_throttled()
    if throttled is None:
        print("⚠️ Watchdog undervoltage: vcgencmd non disponibile su questo host")
        return

    under_now = bool(throttled & 0x1)  # bit 0 = under-voltage NOW

    state: dict = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as fh:
                state = json.load(fh)
        except Exception:
            state = {}

    now = time.time()
    last_alert = float(state.get("last_alert_ts", 0))

    if under_now and (now - last_alert) > COOLDOWN_MIN * 60:
        state["last_alert_ts"] = now
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh)

        volt = measure_volts()
        temp = measure_temp()
        evts = dmesg_events_last_hours()
        evt_str = f"{evts}" if evts >= 0 else "n/d"
        print(
            f"⚠️ UNDERVOLTAGE su {HOST}\n"
            f"• Voltaggio: {volt}V (atteso ~1.2V sotto carico)\n"
            f"• Temp: {temp}°C (non è calore)\n"
            f"• Eventi undervoltage ultime 24h: {evt_str}\n"
            f"• Il SoC sta throttlando → rischio corruzione SD\n"
            f"• Fix a distanza non possibile (alimentatore 5V/3A + cavo corto): "
            f"monitoro io, alert al max ogni {COOLDOWN_MIN} min se persiste"
        )
    # altrimenti silenzio


if __name__ == "__main__":
    main()
