#!/usr/bin/env python3
"""Minimal cron-trigger script that launches the full update."""
import subprocess, sys, os
script = os.path.expanduser("~/.hermes/scripts/update-capreuse-v230-full.py")
result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=300)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])
print("EXIT:", result.returncode)
