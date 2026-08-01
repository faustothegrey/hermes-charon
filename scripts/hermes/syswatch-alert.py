#!/usr/bin/env python3
"""syswatch-alert — Checks alert log and reports if threshold breaches exist."""
import json, os
from pathlib import Path
from datetime import datetime, timezone

ALERT_LOG = Path.home() / ".hermes" / "data" / "syswatch" / "alerts.json"

if not ALERT_LOG.exists():
    print("✅ No alerts (log empty)")
    exit(0)

try:
    alerts = json.loads(ALERT_LOG.read_text())
except (json.JSONDecodeError, OSError):
    print("⚠️ Alert log corrupt")
    exit(0)

if not alerts:
    print("✅ No alerts (list empty)")
    exit(0)

# Show last 5 alerts
recent = alerts[-5:]
now = datetime.now(timezone.utc).timestamp()

active_alerts = [a for a in recent if now - _parse_ts(a.get("timestamp","")) < 3600]

if not active_alerts:
    print("✅ All recent alerts cleared")
    exit(0)

print(f"⚠️ {len(active_alerts)} active alert(s) in last hour:")
for a in active_alerts:
    print(f"  {a.get('metric','?')}: {a.get('value','?')} (threshold: {a.get('threshold','?')})")
    print(f"    {a.get('message','')}")

exit(1 if active_alerts else 0)

def _parse_ts(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()
    except:
        return 0