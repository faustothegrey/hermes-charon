#!/usr/bin/env python3
from __future__ import annotations
"""Generate capability-reuse v2.4.5 reviewer-facing queues."""
import json
import sys
from pathlib import Path

HOME = Path.home()
PLUGIN_DIR = HOME / ".hermes/plugins/capability-reuse"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from review_queue import (  # noqa: E402
    build_review_record,
    filter_organic_review_records,
    load_latest_labels,
    write_jsonl,
    write_markdown_sample,
    write_review_csv,
)

EVENTS = HOME / ".hermes/data/reuse-observer/events.jsonl"
OUTDIR = HOME / ".hermes/data/reuse-aggregati/review"
LABELS = OUTDIR / "human-labels.jsonl"


def load_events(path: Path):
    events = []
    bad = 0
    if not path.exists():
        return events, bad
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            bad += 1
    return events, bad


def is_retrieval(ev):
    return (ev.get("event_type") == "retrieval_event") or ((ev.get("data") or {}).get("event_type") == "retrieval_event")


def main():
    events, bad = load_events(EVENTS)
    labels = load_latest_labels(LABELS)
    records = []
    for ev in events:
        if not is_retrieval(ev):
            continue
        d = ev.get("data") if isinstance(ev.get("data"), dict) else ev
        candidates = d.get("candidates") if isinstance(d.get("candidates"), list) else []
        if not candidates and not d.get("top_capability"):
            continue
        try:
            rec0 = build_review_record(ev, candidate_rank=1)
            latest = labels.get(rec0["review_id"])
            if latest:
                rec0 = build_review_record(ev, candidate_rank=1, latest_label=latest)
            records.append(rec0)
        except Exception:
            continue
    OUTDIR.mkdir(parents=True, exist_ok=True)
    acceptance = [r for r in records if (r.get("request") or {}).get("traffic_type") == "acceptance_test"]
    organic = filter_organic_review_records(records)
    write_jsonl(OUTDIR / "candidates-v245.jsonl", records)
    write_jsonl(OUTDIR / "queue-v245-review.jsonl", records)
    write_review_csv(OUTDIR / "queue-v245-review.csv", records)
    write_jsonl(OUTDIR / "queue-v245-acceptance.jsonl", acceptance)
    write_review_csv(OUTDIR / "queue-v245-acceptance.csv", acceptance)
    write_jsonl(OUTDIR / "queue-v245-organic-review.jsonl", organic)
    write_review_csv(OUTDIR / "queue-v245-organic-review.csv", organic)
    write_markdown_sample(OUTDIR / "human-review-sample.md", organic or records)
    summary = {
        "generated_by": "generate-review-queue-v245",
        "review_schema_version": "1.0",
        "preview_schema_version": "1.0",
        "bad_json_lines": bad,
        "records_total": len(records),
        "acceptance_records": len(acceptance),
        "organic_records": len(organic),
        "outputs": {
            "candidates": str(OUTDIR / "candidates-v245.jsonl"),
            "acceptance_csv": str(OUTDIR / "queue-v245-acceptance.csv"),
            "organic_csv": str(OUTDIR / "queue-v245-organic-review.csv"),
            "sample": str(OUTDIR / "human-review-sample.md"),
        },
    }
    (OUTDIR / "queue-v245-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
