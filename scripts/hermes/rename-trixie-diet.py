#!/usr/bin/env python3
"""Safely change hostname of trixie (192.168.178.136) to 'Diet' when it comes back.
Idempotent: skips if already Diet. No service restarts (HMP/pi.dev bind 0.0.0.0)."""
import json, os, subprocess, sys, time

IP = "192.168.178.136"
NEW = "Diet"
FLAG = "/home/fausto/.hermes/data/trixie_hostname_done.flag"

if os.path.exists(FLAG):
    print("ALREADY DONE — flag exists, exiting")
    sys.exit(0)

def up():
    r = subprocess.run(["ping", "-c", "1", "-W", "2", IP],
                       capture_output=True, timeout=5)
    return r.returncode == 0

# Wait up to 12 min for the machine to come back
deadline = time.time() + 720
while time.time() < deadline:
    if up():
        break
    time.sleep(20)
else:
    print("trixie still DOWN after 12 min — aborting, no change made")
    sys.exit(1)

time.sleep(3)

def ssh(cmd, timeout=20):
    r = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
         f"fausto@{IP}", cmd],
        capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

# 1. Current hostname
rc, out, err = ssh("hostname")
print(f"current hostname: {out or err}")
if out.strip().lower() == NEW.lower():
    print(f"already '{NEW}' — nothing to do")
    open(FLAG, "w").write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    sys.exit(0)

# 2. Check passwordless sudo
rc, out, err = ssh("sudo -n true 2>&1 && echo SUDO_OK || echo SUDO_NEEDS_PASS")
if "SUDO_OK" not in out:
    print("ABORT: passwordless sudo not available on trixie:", out, err)
    sys.exit(2)

# 3. Apply hostname (systemd, Debian 13)
rc, out, err = ssh("sudo -n hostnamectl set-hostname " + NEW)
print("hostnamectl:", out or err, f"(rc={rc})")
if rc != 0:
    print("ABORT: hostnamectl failed")
    sys.exit(2)

# 4. Update /etc/hosts 127.0.1.1 line (keep old name as alias)
rc, out, err = ssh(
    "sudo -n sed -i 's/^127\\.0\\.1\\.1.*/127.0.1.1 Diet trixie/' /etc/hosts && "
    "grep 127.0.1.1 /etc/hosts")
print("hosts:", out or err)

# 5. Verify
rc, out, err = ssh("hostname; hostnamectl status 2>/dev/null | head -3 | tail -2")
print("verify:", out or err)

# 6. Verify services still up (HMP + pi.dev ports)
rc, out, err = ssh("ss -tln | grep -E ':18643|:18644|:8642|:8000|:3000' | wc -l")
print("listeners count:", out or err)

open(FLAG, "w").write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
print("DONE — hostname changed to Diet")
