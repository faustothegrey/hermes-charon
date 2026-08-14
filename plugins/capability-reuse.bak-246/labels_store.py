"""Durable review labels — append-only. Regenerating the queue never erases labels."""
import json, os, threading
from pathlib import Path
from datetime import datetime, timezone

LABELS = Path.home() / ".hermes" / "data" / "reuse-observer" / "review-labels.jsonl"
_lock = threading.Lock()

def save_label(event_id, label, reviewer="manual"):
    with _lock:
        with open(LABELS, 'a') as f:
            f.write(json.dumps({
                "event_id": event_id, "label": label, "reviewer": reviewer,
                "label_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }) + "\n")

def get_labels():
    if not LABELS.exists(): return {}
    out = {}
    for line in LABELS.read_text().splitlines():
        if not line.strip(): continue
        try:
            d = json.loads(line)
            out[d["event_id"]] = d
        except Exception: pass
    return out
