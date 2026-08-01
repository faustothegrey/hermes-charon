#!/usr/bin/env python3
"""Wrapper: runs backup_monitor.py and persists result to status file."""
import subprocess, sys

result = subprocess.run(
    ['python3', '/home/fausto/.hermes/scripts/backup_monitor.py'],
    capture_output=True, text=True, timeout=160
)
print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)