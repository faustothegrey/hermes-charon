#!/usr/bin/env python3
"""Central capability-reuse collector for peer70.

Control-plane stays HMP; data-plane uses local filesystem/SSH where credentials exist.
This script is intentionally pull-based and fail-open: offline peers are marked stale.
"""
import json, os, shutil, subprocess, time
from pathlib import Path

PEERS = {
    "peer70": {"mode": "local"},
    "peer106": {"mode": "ssh", "target": "root@192.168.178.106"},
    "peer84": {"mode": "ssh", "target": "fausto@192.168.178.84"},
    "peer128": {"mode": "ssh", "target": "fausto@192.168.178.112"},
    "peer138": {"mode": "none", "reason": "no SSH/API data-plane configured"},
    "peer58": {"mode": "none", "reason": "data-plane credentials not confirmed"},
}
REMOTE_EVENTS = ".hermes/data/reuse-observer/events.jsonl"
REMOTE_AGG = ".hermes/data/reuse-aggregati/latest.json"
BASE = Path.home() / ".hermes/data/capreuse-central"
RAW = BASE / "raw"
AGG = BASE / "aggregates"
REPORTS = BASE / "reports"
for d in (RAW, AGG, REPORTS):
    d.mkdir(parents=True, exist_ok=True)

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def run(cmd, timeout=30):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)

def copy_local(peer):
    src_events = Path.home() / REMOTE_EVENTS
    src_agg = Path.home() / REMOTE_AGG
    (RAW / peer).mkdir(parents=True, exist_ok=True)
    (AGG / peer).mkdir(parents=True, exist_ok=True)
    if src_events.exists():
        shutil.copy2(src_events, RAW / peer / "events.jsonl")
    if src_agg.exists():
        shutil.copy2(src_agg, AGG / peer / "latest.json")
    return {"status": "ok", "events": src_events.exists(), "aggregate": src_agg.exists()}

def copy_ssh(peer, target):
    (RAW / peer).mkdir(parents=True, exist_ok=True)
    (AGG / peer).mkdir(parents=True, exist_ok=True)
    dest_events = RAW / peer / "events.jsonl"
    dest_agg = AGG / peer / "latest.json"
    # Pull whole files for now; JSONL sizes are small. Later replace with rsync --append-verify/cursors.
    ev = run("scp -q -o BatchMode=yes -o ConnectTimeout=6 %s:%s %s" % (target, REMOTE_EVENTS, dest_events), timeout=45)
    ag = run("scp -q -o BatchMode=yes -o ConnectTimeout=6 %s:%s %s" % (target, REMOTE_AGG, dest_agg), timeout=45)
    return {
        "status": "ok" if ev.returncode == 0 else "partial" if ag.returncode == 0 else "unreachable",
        "events_rc": ev.returncode,
        "aggregate_rc": ag.returncode,
        "events_error": ev.stdout.decode("utf-8", "replace")[-300:] if ev.returncode else "",
        "aggregate_error": ag.stdout.decode("utf-8", "replace")[-300:] if ag.returncode else "",
    }

def count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except Exception:
        return None

results = {"generated_at": now(), "peers": {}}
for peer, cfg in PEERS.items():
    try:
        if cfg["mode"] == "local":
            res = copy_local(peer)
        elif cfg["mode"] == "ssh":
            res = copy_ssh(peer, cfg["target"])
        else:
            res = {"status": "unconfigured", "reason": cfg.get("reason", "")}
    except Exception as e:
        res = {"status": "error", "error": repr(e)}
    evp = RAW / peer / "events.jsonl"
    agp = AGG / peer / "latest.json"
    if evp.exists():
        res["central_events_path"] = str(evp)
        res["central_events_lines"] = count_lines(evp)
        res["central_events_size"] = evp.stat().st_size
    if agp.exists():
        res["central_aggregate_path"] = str(agp)
        res["central_aggregate_size"] = agp.stat().st_size
    results["peers"][peer] = res

latest = REPORTS / "latest.json"
run_report = REPORTS / ("collector-%s.json" % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
for p in (latest, run_report):
    p.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
print(json.dumps(results, indent=2, sort_keys=True))
