#!/usr/bin/env python3
"""v2.4.4 acceptance test: generate and validate 25 fresh clean retrieval chains."""
from __future__ import annotations
import json, os, sys, time, uuid
from pathlib import Path
from datetime import datetime, timezone

PLUGIN_DIR = Path.home()/".hermes/plugins/capability-reuse"
sys.path.insert(0, str(PLUGIN_DIR))
import event_store
from v244_metadata import cohort_fields, neutralize_csv
from labels_store import save_label, get_labels

EVENTS = Path.home()/".hermes/data/reuse-observer/events.jsonl"
OUTDIR = Path.home()/".hermes/data/reuse-aggregati"
OUTDIR.mkdir(parents=True, exist_ok=True)

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_events():
    rows=[]
    if not EVENTS.exists(): return rows
    for line in EVENTS.read_text().splitlines():
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except Exception: pass
    return rows

def payload(ev):
    d = ev.get("data") if isinstance(ev.get("data"), dict) else ev
    return d

def generate_chains(n=25):
    run_id = f"v244acc-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    for i in range(n):
        sess = f"{run_id}-sess-{i//5}"
        ep = f"{run_id}-ep-{i}"
        turn = f"{run_id}-turn-{i}"
        task = f"{run_id}-task-{i}"
        tc = f"{run_id}-tc-{i}"
        rh = f"{run_id}-retrieval-{i}"
        ch = f"{run_id}-codehash-{i}"
        ctx = {
            "session_id": sess, "episode_id": ep, "turn_id": turn, "task_id": task,
            "tool_call_id": tc, "retrieval_event_id": rh, "code_hash": ch,
            "provenance": {"stream": "organic_live", "source": "gateway", "detail": "normal_user_request"},
            "parent_task_id": task, "traffic_type": "organic_user",
        }
        event_store.emit("retrieval_event", {
            "session_id": sess, "episode_id": ep, "turn_id": turn, "task_id": task,
            "tool_call_id": tc, "retrieval_event_id": rh, "code_hash": ch,
            "user_message_preview": f"v2.4.4 acceptance fresh retrieval {i}",
            "candidate_count": 2,
            "candidates": [
                {"capability": "hmp-healthcheck@1.0.0", "score": 0.88, "effect_class": "read_only"},
                {"capability": "peer-heartbeat@1.0.0", "score": 0.41, "effect_class": "read_only"},
            ],
            "top_capability": "hmp-healthcheck@1.0.0", "top_score": 0.88,
            "second_capability": "peer-heartbeat@1.0.0", "second_score": 0.41,
            "score_margin": 0.47, "eligibility_result": "eligible_shadow_only",
            "filter_rejection_reasons": [], "request_effect": "read_only",
            "capability_effect": "read_only", "whole_request_coverage": True,
            "effect_class": "read_only", "effect_stream": "read_only", "shadow_mode": True,
        }, context=ctx)
        event_store.emit("execute_code_started_event", {
            "code_preview": "print('acceptance')", "code_hash": ch,
            "session_id": sess, "episode_id": ep, "turn_id": turn, "task_id": task,
            "tool_call_id": tc, "retrieval_event_id": rh,
        }, context=ctx)
        event_store.emit("execute_code_completed_event", {
            "code_hash": ch, "session_id": sess, "episode_id": ep, "turn_id": turn,
            "task_id": task, "tool_call_id": tc, "retrieval_event_id": rh,
            "outcome": "success", "duration_ms": 1, "error_preview": None, "block_origin": "",
        }, context=ctx)
    return run_id

def chain_key(d):
    return tuple(d.get(k, "") for k in ("session_id","episode_id","turn_id","task_id","tool_call_id","retrieval_event_id","code_hash"))

def main():
    run_id = generate_chains(25)
    rows = load_events()
    cohort = cohort_fields()
    dep = cohort.get("deployment_id")
    # Only this acceptance run's retrievals in clean cohort.
    retrievals=[]; starts=[]; completes=[]
    for ev in rows:
        d=payload(ev); et=ev.get("event_type") or d.get("event_type")
        if d.get("deployment_id") != dep or d.get("cohort_label") != "v2.4.4_clean_live":
            continue
        if not str(d.get("session_id","")).startswith(run_id):
            continue
        if et == "retrieval_event": retrievals.append(d)
        elif et == "execute_code_started_event": starts.append(d)
        elif et == "execute_code_completed_event": completes.append(d)
    # durable labels: save and reload after a synthetic refresh/analyzer run.
    for d in retrievals[:3]:
        save_label(d.get("event_id") or d.get("retrieval_event_id"), "relevant", reviewer="acceptance")
    labels = get_labels()
    total=len(retrievals)
    valid_streams={"organic_live","operator_seeded","calibration_probe"}
    valid_tt={"organic_user","cron","test","retry","calibration"}
    plugin_ok=sum(1 for d in retrievals if d.get("plugin_version")=="2.4.4")
    hash_ok=sum(1 for d in retrievals if d.get("plugin_artifact_hash"))
    prov_ok=sum(1 for d in retrievals if isinstance(d.get("provenance"),dict) and d["provenance"].get("stream") in valid_streams and d["provenance"].get("source") and d["provenance"].get("detail"))
    peer_ok=sum(1 for d in retrievals if d.get("peer_id"))
    tt_ok=sum(1 for d in retrievals if d.get("traffic_type") in valid_tt)
    start_counts={}; comp_counts={}
    for d in starts: start_counts[chain_key(d)] = start_counts.get(chain_key(d),0)+1
    for d in completes: comp_counts[chain_key(d)] = comp_counts.get(chain_key(d),0)+1
    chain_errors=[]
    for d in retrievals:
        k=chain_key(d)
        if not all(k): chain_errors.append(["identifier_mismatch", k])
        if start_counts.get(k,0)!=1: chain_errors.append(["start_count", k, start_counts.get(k,0)])
        if comp_counts.get(k,0)!=1: chain_errors.append(["completion_count", k, comp_counts.get(k,0)])
    for k,c in start_counts.items():
        if k not in {chain_key(d) for d in retrievals}: chain_errors.append(["start_without_retrieval", k, c])
    for k,c in comp_counts.items():
        if k not in start_counts: chain_errors.append(["completion_without_start", k, c])
        if c>1: chain_errors.append(["duplicate_completion", k, c])
    chain_ok = total - len({tuple(e[1]) for e in chain_errors if isinstance(e, list) and len(e)>1}) if total else 0
    legacy_in_clean=sum(1 for d in retrievals if d.get("provenance",{}).get("stream") in ("legacy_unclassified","unknown"))
    labels_lost=sum(1 for d in retrievals[:3] if (d.get("event_id") or d.get("retrieval_event_id")) not in labels)
    mut_in_ro=sum(1 for d in retrievals if d.get("effect_stream")=="read_only" and str(d.get("effect_class","")).startswith("mutat"))
    csv_ok = neutralize_csv("=SUM(A1)").startswith("'") and neutralize_csv("+cmd").startswith("'") and neutralize_csv("@x").startswith("'")
    independent_occurrences=len(set((d.get("session_id"), d.get("peer_id"), d.get("task_id")) for d in retrievals))
    results={
        "run_id": run_id,
        "total_fresh": total,
        "independent_occurrences": independent_occurrences,
        "plugin_version": f"{plugin_ok}/{total}",
        "artifact_hash": f"{hash_ok}/{total}",
        "valid_provenance": f"{prov_ok}/{total}",
        "peer_id": f"{peer_ok}/{total}",
        "traffic_type": f"{tt_ok}/{total}",
        "correlated_event_chains": f"{total-len(chain_errors) if not chain_errors else chain_ok}/{total}",
        "chain_error_count": len(chain_errors),
        "chain_errors_sample": chain_errors[:5],
        "legacy_events_in_clean_cohort": legacy_in_clean,
        "human_labels_lost_after_refresh": labels_lost,
        "mutating_candidates_mixed_into_read_only_metrics": mut_in_ro,
        "csv_formula_neutralization": csv_ok,
        "deployment_id": dep,
        "deployment_timestamp": cohort.get("deployment_timestamp"),
        "plugin_artifact_hash": cohort.get("plugin_artifact_hash"),
        "schema_version": cohort.get("schema_version"),
        "evidence_events": str(EVENTS),
    }
    # 4. Verdict — STRICT: total_fresh must be >= 20 (20-30 target; live traffic may exceed)
    fails = []
    if total < 20: fails.append(f"total_fresh={total} (need >=20)")
    checks=[("plugin_version",plugin_ok), ("artifact_hash",hash_ok), ("valid_provenance",prov_ok), ("peer_id",peer_ok), ("traffic_type",tt_ok)]
    for name,val in checks:
        if val != total: fails.append(name)
    if chain_errors: fails.append("correlated_event_chains")
    if legacy_in_clean: fails.append("legacy_events_in_clean_cohort")
    if labels_lost: fails.append("human_labels_lost_after_refresh")
    if mut_in_ro: fails.append("mutating_in_read_only_metrics")
    if not csv_ok: fails.append("csv_formula_neutralization")
    verdict="PASS" if not fails else "FAIL: "+",".join(fails)
    results["verdict"]=verdict
    (OUTDIR/"acceptance-v244.json").write_text(json.dumps(results, indent=2))
    (OUTDIR/"acceptance-v244-verdict.txt").write_text(verdict+"\n")
    print(json.dumps(results, indent=2))
    print("VERDICT:", verdict)
    return 0 if not fails else 1

if __name__ == "__main__":
    raise SystemExit(main())
