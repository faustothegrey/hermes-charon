#!/usr/bin/env python3
"""Quick aggregate: read events.jsonl, write latest.json."""
import json, time
from pathlib import Path
from collections import Counter

log = Path.home() / ".hermes" / "data" / "reuse-observer" / "events.jsonl"
out = Path.home() / ".hermes" / "data" / "reuse-aggregati" / "latest.json"
out.parent.mkdir(parents=True, exist_ok=True)

if not log.exists():
    out.write_text(json.dumps({"error":"no_events","updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}))
    print("❌ events.jsonl not found")
    exit(1)

lines = [l for l in log.read_text().strip().split("\n") if l.strip()]
types = Counter()
seqs = []
last_retrieval_ts = "?"
last_ec_ts = "?"

for l in lines:
    try:
        e = json.loads(l)
        types[e.get("event_type","?")] += 1
        if e.get("event_type") == "retrieval_event": last_retrieval_ts = e.get("timestamp","?")
        if "execute_code" in e.get("event_type",""): last_ec_ts = e.get("timestamp","?")
    except: pass

agg = {
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "total_events": len(lines),
    "by_type": dict(types),
    "latest_retrieval": last_retrieval_ts[:19] if last_retrieval_ts != "?" else "?",
    "latest_execute_code": last_ec_ts[:19] if last_ec_ts != "?" else "?",
}
out.write_text(json.dumps(agg, indent=2))
print(f"✅ {len(lines)} events → {out}")
print(json.dumps(agg))
