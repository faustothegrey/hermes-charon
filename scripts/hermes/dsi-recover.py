#!/usr/bin/env python3
"""
dsi-recover — Diagnostica e recupero display DSI.

Uso:
  sudo dsi-recover          — diagnostica + recovery automatico
  sudo dsi-recover status    — solo diagnostica
  sudo dsi-recover force     — forza recovery anche senza errori recenti
"""
import os
import sys
import subprocess
import time
from datetime import datetime

HOME = os.path.expanduser("~")
LOG_FILE = os.path.join(HOME, ".hermes", "logs", "dsi-recover.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def run_sudo(cmd, timeout=10):
    try:
        r = subprocess.run(["sudo"] + cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "(timeout)", -1
    except FileNotFoundError as e:
        return f"(missing: {e})", -1


def tee_write(path, data, timeout=5):
    """Write data to a sysfs file via tee."""
    try:
        r = subprocess.run(
            ["sudo", "tee", path],
            input=data,
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return str(e), -1


def check_dsi_error():
    out, _ = run_sudo(["dmesg"], timeout=5)
    recent = []
    for line in out.split("\n"):
        if "tc358762" in line and ("error" in line or "fail" in line):
            recent.append(line)
        if "DSI transfer failed" in line or "transfer interrupt wait timeout" in line:
            recent.append(line)
    return recent


def check_backlight():
    try:
        for d in os.listdir("/sys/class/backlight"):
            with open(f"/sys/class/backlight/{d}/bl_power") as f:
                val = f.read().strip()
            return {"device": d, "bl_power": val, "ok": val == "0"}
    except Exception:
        pass
    return {"device": None, "bl_power": "?", "ok": False}


def check_connector():
    for card in sorted(os.listdir("/sys/class/drm")):
        if "-DSI-" in card:
            status, dpms = "?", "?"
            try:
                with open(f"/sys/class/drm/{card}/status") as f:
                    status = f.read().strip()
            except Exception:
                status = "(assente)"
            try:
                with open(f"/sys/class/drm/{card}/dpms") as f:
                    dpms = f.read().strip()
            except:
                dpms = "?"
            return {"connector": card, "status": status, "dpms": dpms}
    return {"connector": None, "status": "assente", "dpms": "?"}


def check_netboard():
    out, rc = run_sudo(["systemctl", "is-active", "netboard.service"])
    return out.strip() == "active"


def try_reset():
    log("Tentativo reset bridge DSI...")
    run_sudo(["systemctl", "stop", "netboard.service"], timeout=30)
    time.sleep(2)
    log("  netboard fermo, procedo con unbind...")
    tee_write("/sys/bus/mipi-dsi/drivers/tc358762/unbind", "fe700000.dsi.0")
    time.sleep(2)
    log("  unbind fatto, ora rebind...")
    out, rc = tee_write("/sys/bus/mipi-dsi/drivers/tc358762/bind", "fe700000.dsi.0")
    time.sleep(3)
    conn = check_connector()
    if conn["status"] == "connected":
        # Backlight ON
        for d in os.listdir("/sys/class/backlight"):
            tee_write(f"/sys/class/backlight/{d}/bl_power", "0")
        run_sudo(["systemctl", "start", "netboard.service"])
        log(f"✅ Reset riuscito! Connettore: {conn['status']}, DPMS: {conn['dpms']}")
        return True
    else:
        log(f"❌ Reset fallito. Connettore: {conn['status']}")
        # Riavvia netboard comunque
        run_sudo(["systemctl", "start", "netboard.service"])
        return False


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print("🔍 DSI Recover — Diagnostica display\n")
    errors = check_dsi_error()
    conn = check_connector()
    back = check_backlight()
    nb = check_netboard()
    print(f"  NetBoard service:  {'🟢 attivo' if nb else '🔴 fermo'}")
    print(f"  Connettore DSI:    {conn['status']} (dpms: {conn['dpms']})")
    print(f"  Backlight:         {'🟢 acceso' if back.get('ok') else '🔴 spento'} (bl_power={back.get('bl_power','?')})")
    print(f"  Errori dmesg DSI:  {len(errors)}")
    for e in errors[-3:]:
        print(f"    └─ {e}")
    if action == "status":
        return
    should_recover = action == "force" or (action == "auto" and (len(errors) > 0 or conn["status"] != "connected"))
    if should_recover:
        print("\n⚡ Tentativo recovery...\n")
        success = try_reset()
        if success:
            print("\n✅ Display DSI recuperato! NetBoard riavviato.")
        else:
            print("\n❌ Recovery fallito — serve reboot.")
            print("\n   Per riavviare:  sudo reboot")
    else:
        print("\n✅ Nessun problema rilevato.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("❌ Questo script richiede sudo. Esegui: sudo dsi-recover")
        sys.exit(1)
    main()
