#!/usr/bin/env python3
"""Copy plugin files and restart Hermes gateway."""
import shutil, os, subprocess, sys, time
from pathlib import Path

src = Path.home() / ".hermes" / "skills" / "hermes" / "capability-reuse" / "plugin"
dst = Path.home() / ".hermes" / "plugins" / "capability-reuse"

# 1. Copy plugin
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
print(f"✅ Plugin copied: {src} → {dst}")

# 2. Verify files
files = list(dst.rglob("*.py")) + [dst / "plugin.yaml"]
for f in files:
    print(f"   {f.name} ({f.stat().st_size}B)")
print(f"   Total: {len(files)} files")

# 3. Restart gateway via systemd
try:
    result = subprocess.run(
        ["systemctl", "--user", "restart", "hermes-gateway"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("✅ Gateway restart initiated")
    else:
        print(f"❌ systemctl failed: {result.stderr.strip()}")
        # Try kill approach
        try:
            pid = subprocess.run(
                ["pgrep", "-f", "hermes.*gateway"],
                capture_output=True, text=True, timeout=5
            )
            if pid.stdout.strip():
                for p in pid.stdout.strip().split("\n"):
                    subprocess.run(["kill", "-9", p], timeout=5)
                    print(f"   Killed PID {p}")
                print("⏳ Waiting for systemd auto-restart...")
                time.sleep(15)
            else:
                print("❌ No gateway process found")
        except Exception as e:
            print(f"❌ Kill failed: {e}")
except Exception as e:
    print(f"❌ Restart failed: {e}")

# 4. Wait and health check
time.sleep(10)
try:
    r = subprocess.run(
        ["curl", "-sf", "http://localhost:18643/hmp/agent-card"],
        capture_output=True, text=True, timeout=5
    )
    if r.returncode == 0:
        print(f"✅ Gateway healthy: {r.stdout.strip()[:120]}")
    else:
        print("❌ Gateway not responding after restart")
except Exception as e:
    print(f"❌ Health check failed: {e}")

print("\nDone.")
sys.exit(0)
